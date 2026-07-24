# Shared desktop boundary

ClassicUI and ModernUI receive the same `backend` QObject from
`apps/desktop/main.py`.  Shared project, pipeline, viewer, runtime, and export
behavior belongs in Python and must not be duplicated in either QML tree.
