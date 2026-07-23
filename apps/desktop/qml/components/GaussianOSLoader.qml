import QtQuick

Item {
    id: root

    property bool running: false
    property bool loop: true
    property real durationSeconds: 2.4
    property color backgroundColor: "#f7f6f3"
    property color frameColor: "#aab5c6"
    property color dotColor: "#126df5"
    property bool showCompleteWhenStopped: true
    property bool reducedMotion: false

    // A non-negative value freezes the component at a deterministic point in
    // the authoritative 0..1 timeline. It is intended for preview and visual QA.
    property real frameProgress: -1

    readonly property real viewBoxX: 180
    readonly property real viewBoxY: 120
    readonly property real viewBoxWidth: 760
    readonly property real viewBoxHeight: 760

    readonly property real drawShare: 0.49
    readonly property real holdShare: 0.15
    readonly property real eraseShare: 0.36
    readonly property var localSegmentBezier: [
        0.12435080307307722,
        0.07980046356788748,
        0.7913197843871304,
        0.6574632584118638
    ]
    readonly property var globalIntroBezier: [
        0.714656658682506,
        0,
        0.30834223399211613,
        0.9759421141426933
    ]
    readonly property var globalOutroBezier: [
        0.20868021561286962,
        0,
        0.23167917262572765,
        1
    ]
    readonly property var segmentShares: [0.1, 0.2, 0.15, 0.18, 0.18, 0.13, 0.16]

    // The point order is copied verbatim from s0..s6 in the reference SVG.
    readonly property var frameSegments: [
        [762, 267, 625, 185],
        [625, 185, 355, 350],
        [355, 350, 355, 643],
        [355, 643, 625, 802],
        [625, 802, 897, 643],
        [897, 643, 897, 345],
        [897, 345, 625, 500]
    ]

    // The paths remain in the exact DOM order used by the reference animation.
    readonly property var dotPaths: [
        [[486, 275], [626, 350], [766, 275]],
        [[486, 275], [486, 417]],
        [[626, 350], [626, 497]],
        [[766, 275], [766, 417]],
        [[486, 417], [626, 497], [766, 417]],
        [[371, 497], [498, 570], [626, 497]],
        [[371, 497], [486, 417]],
        [[498, 570], [498, 708]],
        [[626, 497], [626, 644]],
        [[498, 708], [626, 644]],
        [[626, 497], [759, 576], [881, 497]],
        [[881, 497], [766, 417]],
        [[759, 576], [759, 708]],
        [[626, 644], [759, 708]]
    ]

    readonly property real _durationMs: Math.max(1, durationSeconds * 1000)
    property real _elapsedMs: 0

    implicitWidth: 720
    implicitHeight: 720
    Accessible.role: Accessible.Graphic
    Accessible.name: "GaussianOS"
    Accessible.description: running && !reducedMotion
        ? "GaussianOS reconstruction animation"
        : "GaussianOS logo"

    function play() {
        if (running) {
            if (!cycleAnimation.running)
                _startCycle()
            return
        }
        running = true
    }

    function stop() {
        running = false
    }

    function restart() {
        if (!running) {
            running = true
            return
        }
        _startCycle()
    }

    function requestPaint() {
        logoCanvas.requestPaint()
    }

    function _startCycle() {
        cycleAnimation.stop()
        _elapsedMs = 0
        logoCanvas.requestPaint()
        if (!reducedMotion && frameProgress < 0 && visible)
            cycleAnimation.restart()
    }

    function _settle() {
        cycleAnimation.stop()
        _elapsedMs = 0
        logoCanvas.requestPaint()
    }

    function _cubicAt(t, p1, p2) {
        var inverse = 1 - t
        return 3 * inverse * inverse * t * p1
            + 3 * inverse * t * t * p2
            + t * t * t
    }

    // Exact port of the reference's y(progress) -> x(time) inversion.
    function _timeForProgress(bezier, progress) {
        if (progress <= 0)
            return 0
        if (progress >= 1)
            return 1
        var low = 0
        var high = 1
        for (var iteration = 0; iteration < 40; ++iteration) {
            var parameter = (low + high) / 2
            var value = _cubicAt(parameter, bezier[1], bezier[3])
            if (value < progress)
                low = parameter
            else
                high = parameter
        }
        var solved = (low + high) / 2
        return _cubicAt(solved, bezier[0], bezier[2])
    }

    // CSS cubic-bezier evaluation: invert x(time), then evaluate y(progress).
    function _cssBezierProgress(bezier, time) {
        if (time <= 0)
            return 0
        if (time >= 1)
            return 1
        var low = 0
        var high = 1
        for (var iteration = 0; iteration < 40; ++iteration) {
            var parameter = (low + high) / 2
            var value = _cubicAt(parameter, bezier[0], bezier[2])
            if (value < time)
                low = parameter
            else
                high = parameter
        }
        var solved = (low + high) / 2
        return _cubicAt(solved, bezier[1], bezier[3])
    }

    function _windowProgress(now, start, end, easingBezier) {
        if (now <= start)
            return 0
        if (now >= end)
            return 1
        var duration = Math.max(16, end - start)
        return _cssBezierProgress(easingBezier, (now - start) / duration)
    }

    function _drawDotPath(ctx, points, opacity, scaleValue) {
        if (opacity <= 0)
            return
        ctx.save()
        ctx.globalAlpha = opacity
        ctx.translate(560, 500)
        ctx.scale(scaleValue, scaleValue)
        ctx.translate(-560, -500)
        ctx.beginPath()
        ctx.moveTo(points[0][0], points[0][1])
        for (var pointIndex = 1; pointIndex < points.length; ++pointIndex)
            ctx.lineTo(points[pointIndex][0], points[pointIndex][1])
        ctx.strokeStyle = dotColor
        ctx.lineWidth = 8
        ctx.lineCap = "round"
        ctx.lineJoin = "miter"
        // Qt's Canvas forwards dash lengths to QPen, whose dash units are
        // multiples of lineWidth. Divide the SVG user-unit values by 8.
        ctx.setLineDash([0.1 / 8, 15.5 / 8])
        ctx.lineDashOffset = 0
        ctx.stroke()
        ctx.restore()
    }

    function _drawFrameSegment(ctx, segment, startFraction, endFraction) {
        if (endFraction <= startFraction)
            return
        var x1 = segment[0] + (segment[2] - segment[0]) * startFraction
        var y1 = segment[1] + (segment[3] - segment[1]) * startFraction
        var x2 = segment[0] + (segment[2] - segment[0]) * endFraction
        var y2 = segment[1] + (segment[3] - segment[1]) * endFraction
        ctx.save()
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.strokeStyle = frameColor
        ctx.lineWidth = 54
        ctx.lineCap = "round"
        ctx.lineJoin = "round"
        ctx.setLineDash([])
        ctx.stroke()
        ctx.restore()
    }

    function _paintComplete(ctx) {
        for (var dotIndex = 0; dotIndex < dotPaths.length; ++dotIndex)
            _drawDotPath(ctx, dotPaths[dotIndex], 1, 1)
        for (var segmentIndex = 0; segmentIndex < frameSegments.length; ++segmentIndex)
            _drawFrameSegment(ctx, frameSegments[segmentIndex], 0, 1)
    }

    function _paintTimeline(ctx, elapsed) {
        var drawMs = _durationMs * drawShare
        var holdMs = _durationMs * holdShare
        var eraseMs = _durationMs * eraseShare
        var eraseBase = drawMs + holdMs

        // Dotted cube is painted first so every overlap remains below the G.
        var dotCount = dotPaths.length
        for (var dotIndex = 0; dotIndex < dotCount; ++dotIndex) {
            var order = dotIndex / Math.max(1, dotCount - 1)
            var introProgress = 0.16 + (0.88 - 0.16) * order
            var outroProgress = 0.16 + (0.88 - 0.16) * order
            var introTime = _timeForProgress(globalIntroBezier, introProgress) * drawMs
            var outroTime = eraseBase
                + _timeForProgress(globalOutroBezier, outroProgress) * eraseMs
            var intro = _windowProgress(
                elapsed, introTime, introTime + 180, localSegmentBezier)
            var opacity = intro
            if (elapsed >= outroTime)
                opacity = 1 - Math.min(1, Math.max(0, (elapsed - outroTime) / 220))
            _drawDotPath(
                ctx,
                dotPaths[dotIndex],
                opacity,
                0.985 + 0.015 * intro)
        }

        var shareTotal = 0
        for (var shareIndex = 0; shareIndex < segmentShares.length; ++shareIndex)
            shareTotal += segmentShares[shareIndex]

        var accumulatedShare = 0
        for (var segmentIndex = 0;
             segmentIndex < frameSegments.length;
             ++segmentIndex) {
            var startBoundary = accumulatedShare / shareTotal
            accumulatedShare += segmentShares[segmentIndex]
            var endBoundary = accumulatedShare / shareTotal
            var drawStart = _timeForProgress(
                globalIntroBezier, startBoundary) * drawMs
            var drawEnd = _timeForProgress(
                globalIntroBezier, endBoundary) * drawMs
            var eraseStart = eraseBase
                + _timeForProgress(globalOutroBezier, startBoundary) * eraseMs
            var eraseEnd = eraseBase
                + _timeForProgress(globalOutroBezier, endBoundary) * eraseMs

            var startFraction = 0
            var endFraction = _windowProgress(
                elapsed, drawStart, drawEnd, localSegmentBezier)
            if (elapsed >= eraseStart)
                startFraction = _windowProgress(
                    elapsed, eraseStart, eraseEnd, localSegmentBezier)
            _drawFrameSegment(
                ctx,
                frameSegments[segmentIndex],
                startFraction,
                endFraction)
        }
    }

    onRunningChanged: {
        if (running)
            _startCycle()
        else
            _settle()
    }
    onLoopChanged: {
        if (running)
            _startCycle()
    }
    onDurationSecondsChanged: {
        if (running)
            _startCycle()
        else
            requestPaint()
    }
    onReducedMotionChanged: {
        if (running && !reducedMotion)
            _startCycle()
        else
            _settle()
    }
    onFrameProgressChanged: {
        if (frameProgress >= 0)
            cycleAnimation.stop()
        else if (running)
            _startCycle()
        requestPaint()
    }
    onShowCompleteWhenStoppedChanged: requestPaint()
    onFrameColorChanged: requestPaint()
    onDotColorChanged: requestPaint()
    onVisibleChanged: {
        if (!visible)
            cycleAnimation.stop()
        else if (running)
            _startCycle()
        else
            requestPaint()
    }
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    Component.onCompleted: {
        if (running)
            _startCycle()
        else
            requestPaint()
    }
    Component.onDestruction: cycleAnimation.stop()

    Rectangle {
        anchors.fill: parent
        color: root.backgroundColor
    }

    Canvas {
        id: logoCanvas
        anchors.fill: parent
        antialiasing: true
        renderTarget: Canvas.Image
        renderStrategy: Canvas.Immediate

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.clearRect(0, 0, width, height)

            var scaleValue = Math.min(
                width / root.viewBoxWidth,
                height / root.viewBoxHeight)
            var paintedWidth = root.viewBoxWidth * scaleValue
            var paintedHeight = root.viewBoxHeight * scaleValue
            ctx.save()
            ctx.translate(
                (width - paintedWidth) / 2,
                (height - paintedHeight) / 2)
            ctx.scale(scaleValue, scaleValue)
            ctx.translate(-root.viewBoxX, -root.viewBoxY)

            if (root.reducedMotion
                    || (root.frameProgress < 0
                        && !root.running
                        && root.showCompleteWhenStopped)) {
                root._paintComplete(ctx)
            } else {
                var elapsed = root.frameProgress >= 0
                    ? Math.min(1, Math.max(0, root.frameProgress))
                        * root._durationMs
                    : root._elapsedMs
                root._paintTimeline(ctx, elapsed)
            }
            ctx.restore()
        }
    }

    NumberAnimation {
        id: cycleAnimation
        target: root
        property: "_elapsedMs"
        from: 0
        to: root._durationMs
        duration: Math.round(root._durationMs)
        easing.type: Easing.Linear
        loops: root.loop ? Animation.Infinite : 1
        onFinished: {
            root._elapsedMs = root._durationMs
            root.requestPaint()
        }
    }

    on_ElapsedMsChanged: logoCanvas.requestPaint()
}
