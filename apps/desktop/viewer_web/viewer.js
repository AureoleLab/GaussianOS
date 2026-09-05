'use strict';

const canvas = document.querySelector('#gl');
const errorBox = document.querySelector('#error');
const gl = canvas.getContext('webgl2', {
  alpha: false,
  antialias: false,
  powerPreference: 'high-performance',
});

function fail(message) {
  errorBox.textContent = 'Viewer load error: ' + message;
  errorBox.style.display = 'block';
  document.querySelector('#artifact').textContent = 'Load failed';
  document.title = 'error|' + message;
}
if (!gl) fail('WebGL2 is unavailable');
window.addEventListener('error', event => fail(event.message || 'JavaScript error'));
window.addEventListener('unhandledrejection', event => fail(event.reason && event.reason.message ? event.reason.message : String(event.reason)));

const AXIS_COLORS = [[0.92, 0.18, 0.16], [0.22, 0.72, 0.24], [0.18, 0.42, 0.94]];
const IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const BLENDER_FROM_SCENE = [1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1];
const DEFAULT_PLACEMENT = {
  translation: [0, 0, 0], rotation_xyz_degrees: [0, 0, 0],
  scale_xyz: [1, 1, 1], scale_locked: true,
};

function add(a, b) { return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]; }
function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
function mul(a, s) { return [a[0] * s, a[1] * s, a[2] * s]; }
function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
function cross(a, b) { return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]; }
function norm(a) { const n = Math.hypot(...a) || 1; return mul(a, 1 / n); }
function clonePlacement(value) {
  const source = value || DEFAULT_PLACEMENT;
  return {
    translation: [...source.translation].map(Number),
    rotation_xyz_degrees: [...source.rotation_xyz_degrees].map(Number),
    scale_xyz: [...source.scale_xyz].map(Number),
    scale_locked: source.scale_locked !== false,
  };
}
function multiply4(a, b) {
  const out = new Array(16).fill(0);
  for (let r = 0; r < 4; r++) for (let c = 0; c < 4; c++)
    for (let k = 0; k < 4; k++) out[r * 4 + c] += a[r * 4 + k] * b[k * 4 + c];
  return out;
}
function composePlacement(value) {
  const p = clonePlacement(value), [tx, ty, tz] = p.translation;
  const [rx, ry, rz] = p.rotation_xyz_degrees.map(v => v * Math.PI / 180);
  const [sx, sy, sz] = p.scale_xyz;
  const cx = Math.cos(rx), xx = Math.sin(rx), cy = Math.cos(ry), yy = Math.sin(ry), cz = Math.cos(rz), zz = Math.sin(rz);
  const t = [1, 0, 0, tx, 0, 1, 0, ty, 0, 0, 1, tz, 0, 0, 0, 1];
  const mx = [1, 0, 0, 0, 0, cx, -xx, 0, 0, xx, cx, 0, 0, 0, 0, 1];
  const my = [cy, 0, yy, 0, 0, 1, 0, 0, -yy, 0, cy, 0, 0, 0, 0, 1];
  const mz = [cz, -zz, 0, 0, zz, cz, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  const s = [sx, 0, 0, 0, 0, sy, 0, 0, 0, 0, sz, 0, 0, 0, 0, 1];
  return [mz, my, mx, s, BLENDER_FROM_SCENE].reduce((result, matrix) => multiply4(result, matrix), t);
}
function rowsToGL(m) {
  return new Float32Array([m[0], m[4], m[8], m[12], m[1], m[5], m[9], m[13], m[2], m[6], m[10], m[14], m[3], m[7], m[11], m[15]]);
}
function transformPoint(m, p) {
  return [m[0] * p[0] + m[1] * p[1] + m[2] * p[2] + m[3], m[4] * p[0] + m[5] * p[1] + m[6] * p[2] + m[7], m[8] * p[0] + m[9] * p[1] + m[10] * p[2] + m[11]];
}
function transformDirection(m, p) {
  return norm([m[0] * p[0] + m[1] * p[1] + m[2] * p[2], m[4] * p[0] + m[5] * p[1] + m[6] * p[2], m[8] * p[0] + m[9] * p[1] + m[10] * p[2]]);
}
function matrixPoint(m, p) {
  return [m[0][0] * p[0] + m[0][1] * p[1] + m[0][2] * p[2] + m[0][3], m[1][0] * p[0] + m[1][1] * p[1] + m[1][2] * p[2] + m[1][3], m[2][0] * p[0] + m[2][1] * p[1] + m[2][2] * p[2] + m[2][3]];
}

function shader(type, source) {
  const value = gl.createShader(type); gl.shaderSource(value, source); gl.compileShader(value);
  if (!gl.getShaderParameter(value, gl.COMPILE_STATUS)) throw Error(gl.getShaderInfoLog(value));
  return value;
}
function program(vertex, fragment) {
  const value = gl.createProgram(); gl.attachShader(value, shader(gl.VERTEX_SHADER, vertex)); gl.attachShader(value, shader(gl.FRAGMENT_SHADER, fragment)); gl.linkProgram(value);
  if (!gl.getProgramParameter(value, gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(value));
  return value;
}

const splatVertex = `#version 300 es
precision highp float; precision highp int;
uniform sampler2D dataTex; uniform ivec2 texSize; uniform mat4 sceneRoot,view,proj; uniform vec3 eye; uniform vec2 viewport;
in vec2 corner; in float orderIndex; out vec2 local; out vec3 color; out float baseOpacity;
vec4 getT(int g,int o){int p=g*19+o;return texelFetch(dataTex,ivec2(p%texSize.x,p/texSize.x),0);}
mat3 qmat(vec4 q){q=normalize(q);float w=q.x,x=q.y,y=q.z,z=q.w;return mat3(1.-2.*(y*y+z*z),2.*(x*y+z*w),2.*(x*z-y*w),2.*(x*y-z*w),1.-2.*(x*x+z*z),2.*(y*z+x*w),2.*(x*z+y*w),2.*(y*z-x*w),1.-2.*(x*x+y*y));}
vec3 sh(int g,vec3 d){vec3 r=.2820947918*getT(g,3).rgb;float x=d.x,y=d.y,z=d.z;r+=(-.4886025119*y)*getT(g,4).rgb+(.4886025119*z)*getT(g,5).rgb+(-.4886025119*x)*getT(g,6).rgb;r+=(1.0925484306*x*y)*getT(g,7).rgb+(-1.0925484306*y*z)*getT(g,8).rgb+(.3153915653*(3.*z*z-1.))*getT(g,9).rgb+(-1.0925484306*x*z)*getT(g,10).rgb+(.5462742153*(x*x-y*y))*getT(g,11).rgb;r+=(-.5900435899*y*(3.*x*x-y*y))*getT(g,12).rgb+(2.8906114426*x*y*z)*getT(g,13).rgb+(-.4570457995*y*(5.*z*z-1.))*getT(g,14).rgb+(.3731763326*z*(5.*z*z-3.))*getT(g,15).rgb+(-.4570457995*x*(5.*z*z-1.))*getT(g,16).rgb+(1.4453057215*z*(x*x-y*y))*getT(g,17).rgb+(-.5900435899*x*(x*x-3.*y*y))*getT(g,18).rgb;return max(r+vec3(.5),vec3(0.));}
void main(){int g=int(orderIndex+.5);vec4 a=getT(g,0),b=getT(g,1),cc=getT(g,2);vec3 mean=(sceneRoot*vec4(a.xyz,1)).xyz,sc=exp(b.xyz);mat3 R=mat3(sceneRoot)*qmat(vec4(b.w,cc.xyz));vec3 vp=(view*vec4(mean,1)).xyz;if(vp.z>=-.01){gl_Position=vec4(2,2,2,1);local=vec2(2);color=vec3(0);baseOpacity=0.;return;}float z=-vp.z;float fy=proj[1][1],fx=proj[0][0];mat3 B=mat3(view)*R*mat3(sc.x,0,0,0,sc.y,0,0,0,sc.z);vec2 d0=vec2(fx*(B[0].x*z+vp.x*B[0].z)/(z*z),fy*(B[0].y*z+vp.y*B[0].z)/(z*z));vec2 d1=vec2(fx*(B[1].x*z+vp.x*B[1].z)/(z*z),fy*(B[1].y*z+vp.y*B[1].z)/(z*z));vec2 d2=vec2(fx*(B[2].x*z+vp.x*B[2].z)/(z*z),fy*(B[2].y*z+vp.y*B[2].z)/(z*z));mat2 cov=mat2(dot(vec3(d0.x,d1.x,d2.x),vec3(d0.x,d1.x,d2.x))+4./(viewport.x*viewport.x),dot(vec3(d0.x,d1.x,d2.x),vec3(d0.y,d1.y,d2.y)),dot(vec3(d0.x,d1.x,d2.x),vec3(d0.y,d1.y,d2.y)),dot(vec3(d0.y,d1.y,d2.y),vec3(d0.y,d1.y,d2.y))+4./(viewport.y*viewport.y));float tr=cov[0][0]+cov[1][1],det=cov[0][0]*cov[1][1]-cov[0][1]*cov[1][0],l1=max(tr*.5+sqrt(max(tr*tr*.25-det,0.)),1e-8),l2=max(tr-l1,1e-8),footprint=3.*sqrt(l1);if(footprint>.35){float clampScale=.35/footprint;l1*=clampScale*clampScale;l2*=clampScale*clampScale;}vec2 e1=normalize(vec2(cov[0][1],l1-cov[0][0])+vec2(1e-10)),e2=vec2(-e1.y,e1.x),off=3.*(corner.x*sqrt(l1)*e1+corner.y*sqrt(l2)*e2);vec4 clip=proj*vec4(vp,1);clip.xy+=off*clip.w;gl_Position=clip;local=corner;color=sh(g,normalize(inverse(mat3(sceneRoot))*(mean-eye)));baseOpacity=1./(1.+exp(-a.w));}`;
const splatFragment = `#version 300 es
precision highp float;in vec2 local;in vec3 color;in float baseOpacity;out vec4 outColor;void main(){float r2=dot(local,local);if(r2>1.)discard;float a=baseOpacity*exp(-4.5*r2);if(a<.003)discard;outColor=vec4(color,a);}`;
const lineVertex = `#version 300 es
precision highp float;uniform mat4 root,view,proj;in vec3 position;in vec3 inColor;out vec3 color;void main(){gl_Position=proj*view*root*vec4(position,1);gl_PointSize=3.;color=inColor;}`;
const lineFragment = `#version 300 es
precision highp float;in vec3 color;out vec4 outColor;void main(){outColor=vec4(color,1);}`;
const pointVertex = `#version 300 es
precision highp float;uniform mat4 root,view,proj;uniform float pointSize;uniform vec3 fallbackColor;in vec3 position;in vec3 inColor;out vec3 color;void main(){gl_Position=proj*view*root*vec4(position,1);gl_PointSize=pointSize;color=inColor.r<0.?fallbackColor:inColor;}`;
const pointFragment = `#version 300 es
precision highp float;in vec3 color;out vec4 outColor;void main(){vec2 d=gl_PointCoord*2.-1.;if(dot(d,d)>1.)discard;outColor=vec4(color,1);}`;

const splatProgram = program(splatVertex, splatFragment), lineProgram = program(lineVertex, lineFragment), pointProgram = program(pointVertex, pointFragment);
let count = 0, rawMeans = null, order = null, sortIds = [], orderBuffer = null, dataTexture = null, texW = 2048, texH = 1;
let pointVAO = null, pointCount = 0, cameraVAO = null, cameraCount = 0, cameraPathVAO = null, cameraPathCount = 0, activeCameraVAO = null, activeCameraCount = 0;
let gridVAO = null, gridCount = 0, axesVAO = null, axesCount = 0, gizmoVAO = null, gizmoCount = 0, gridSpacing = 0;
let meta = null, placement = clonePlacement(DEFAULT_PLACEMENT), sceneRoot = [...IDENTITY], viewerBridge = null, bridgeReady = false;
let cameraFrustumDepth = .01;
const appearance = {background: '#383838', showGrid: true, showAxes: true, cameraOverlay: 'selected', showCameraPath: false, showPoints: false};

const quad = new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]);
const splatVAO = gl.createVertexArray(); gl.bindVertexArray(splatVAO);
const quadBuffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, quadBuffer); gl.bufferData(gl.ARRAY_BUFFER, quad, gl.STATIC_DRAW);
let location = gl.getAttribLocation(splatProgram, 'corner'); gl.enableVertexAttribArray(location); gl.vertexAttribPointer(location, 2, gl.FLOAT, false, 0, 0);
orderBuffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, orderBuffer); location = gl.getAttribLocation(splatProgram, 'orderIndex'); gl.enableVertexAttribArray(location); gl.vertexAttribPointer(location, 1, gl.FLOAT, false, 0, 0); gl.vertexAttribDivisor(location, 1);

function header(buffer) {
  const bytes = new Uint8Array(buffer), needle = new TextEncoder().encode('end_header\n'); let end = -1;
  outer: for (let i = 0; i <= bytes.length - needle.length; i++) { for (let j = 0; j < needle.length; j++) if (bytes[i + j] !== needle[j]) continue outer; end = i + needle.length; break; }
  if (end < 0) throw Error('PLY end_header missing');
  const lines = new TextDecoder().decode(bytes.slice(0, end)).trim().split(/\r?\n/); let n = 0; const props = [];
  for (const line of lines) { const fields = line.split(/\s+/); if (fields[0] === 'element' && fields[1] === 'vertex') n = +fields[2]; if (fields[0] === 'property' && fields.length === 3) props.push(fields[2]); }
  return {end, n, props};
}
function parseGaussian(buffer) {
  const h = header(buffer), view = new DataView(buffer, h.end), stride = h.props.length * 4, map = Object.fromEntries(h.props.map((name, index) => [name, index * 4]));
  const packed = new Float32Array(h.n * 76); rawMeans = new Float32Array(h.n * 3); const get = (index, name) => view.getFloat32(index * stride + map[name], true);
  const rest = h.props.filter(name => name.startsWith('f_rest_')).length, degree = Math.round(Math.sqrt(rest / 3 + 1)) - 1;
  for (let i = 0; i < h.n; i++) { const base = i * 76, x = get(i, 'x'), y = get(i, 'y'), z = get(i, 'z'); rawMeans.set([x, y, z], i * 3); packed.set([x, y, z, get(i, 'opacity')], base); packed.set([get(i, 'scale_0'), get(i, 'scale_1'), get(i, 'scale_2'), get(i, 'rot_0')], base + 4); packed.set([get(i, 'rot_1'), get(i, 'rot_2'), get(i, 'rot_3'), degree], base + 8); packed.set([get(i, 'f_dc_0'), get(i, 'f_dc_1'), get(i, 'f_dc_2'), 0], base + 12); const coefficients = (degree + 1) ** 2; for (let j = 1; j < 16; j++) { const value = [0, 0, 0, 0]; if (j < coefficients) for (let channel = 0; channel < 3; channel++) value[channel] = get(i, 'f_rest_' + (channel * (coefficients - 1) + j - 1)); packed.set(value, base + (3 + j) * 4); } }
  count = h.n; texH = Math.ceil(count * 19 / texW); const padded = new Float32Array(texW * texH * 4); padded.set(packed); dataTexture = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, dataTexture); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA32F, texW, texH, 0, gl.RGBA, gl.FLOAT, padded);
  order = new Float32Array(count); sortIds = Array.from({length: count}, (_, index) => index); for (let i = 0; i < count; i++) order[i] = i; gl.bindBuffer(gl.ARRAY_BUFFER, orderBuffer); gl.bufferData(gl.ARRAY_BUFFER, order, gl.DYNAMIC_DRAW); document.querySelector('#count').textContent = count.toLocaleString() + ' Gaussians';
}
function makeLineVAO(data) {
  const vao = gl.createVertexArray(); gl.bindVertexArray(vao); const buffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
  const p = gl.getAttribLocation(lineProgram, 'position'), c = gl.getAttribLocation(lineProgram, 'inColor'); gl.enableVertexAttribArray(p); gl.vertexAttribPointer(p, 3, gl.FLOAT, false, 24, 0); gl.enableVertexAttribArray(c); gl.vertexAttribPointer(c, 3, gl.FLOAT, false, 24, 12); return vao;
}
function makePointVAO(data) {
  const vao = gl.createVertexArray(); gl.bindVertexArray(vao); const buffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
  const p = gl.getAttribLocation(pointProgram, 'position'), c = gl.getAttribLocation(pointProgram, 'inColor'); gl.enableVertexAttribArray(p); gl.vertexAttribPointer(p, 3, gl.FLOAT, false, 24, 0); gl.enableVertexAttribArray(c); gl.vertexAttribPointer(c, 3, gl.FLOAT, false, 24, 12); return vao;
}
function parsePoints(buffer) {
  const h = header(buffer), view = new DataView(buffer, h.end); let stride = 0; const offsets = {}; for (const property of h.props) { offsets[property] = stride; stride += ['red', 'green', 'blue', 'alpha'].includes(property) ? 1 : 4; }
  const output = new Float32Array(h.n * 6); for (let i = 0; i < h.n; i++) { output[i * 6] = view.getFloat32(i * stride + offsets.x, true); output[i * 6 + 1] = view.getFloat32(i * stride + offsets.y, true); output[i * 6 + 2] = view.getFloat32(i * stride + offsets.z, true); for (let channel = 0; channel < 3; channel++) { const name = ['red', 'green', 'blue'][channel]; output[i * 6 + 3 + channel] = name in offsets ? view.getUint8(i * stride + offsets[name]) / 255 : -1; } }
  pointCount = h.n; pointVAO = makePointVAO(output);
}
function pushSegment(output, a, b, color) { output.push(...a, ...color, ...b, ...color); }
function appendCameraFrustum(output, record, depth, color) {
  const matrix = record.cam2world, origin = [matrix[0][3], matrix[1][3], matrix[2][3]], k = record.intrinsics, width = record.width, height = record.height;
  const corners = [[0, 0], [width, 0], [width, height], [0, height]].map(([u, v]) => matrixPoint(matrix, [(u - k[0][2]) / k[0][0] * depth, (v - k[1][2]) / k[1][1] * depth, depth]));
  for (const corner of corners) pushSegment(output, origin, corner, color); for (let i = 0; i < 4; i++) pushSegment(output, corners[i], corners[(i + 1) % 4], color);
}
function buildCameraGeometry() {
  const path = [], frusta = [], positions = meta.camera_positions || [];
  for (let i = 1; i < positions.length; i++) pushSegment(path, positions[i - 1], positions[i], [1, .55, .16]);
  const diagonal = Math.max(.01, Math.hypot(...sub(meta.bounds_max, meta.bounds_min))), steps = [];
  for (let i = 1; i < positions.length; i++) { const step = Math.hypot(...sub(positions[i], positions[i - 1])); if (Number.isFinite(step) && step > diagonal * 1e-6) steps.push(step); }
  steps.sort((a, b) => a - b); const medianStep = steps.length ? steps[Math.floor(steps.length / 2)] : diagonal * .032;
  cameraFrustumDepth = Math.max(diagonal * .002, Math.min(diagonal * .015, medianStep * .25));
  for (const record of meta.cameras || []) appendCameraFrustum(frusta, record, cameraFrustumDepth, [1, .45, .08]);
  cameraPathCount = path.length / 6; cameraPathVAO = path.length ? makeLineVAO(new Float32Array(path)) : null; cameraCount = frusta.length / 6; cameraVAO = frusta.length ? makeLineVAO(new Float32Array(frusta)) : null;
}
function highlightCamera(record) {
  activeCameraVAO = null; activeCameraCount = 0; if (!record || !meta) return; const matrix = record.cam2world, origin = [matrix[0][3], matrix[1][3], matrix[2][3]], output = [];
  appendCameraFrustum(output, record, cameraFrustumDepth, [1, .72, .18]); const size = cameraFrustumDepth * .8;
  for (let axis = 0; axis < 3; axis++) pushSegment(output, origin, add(origin, mul([matrix[0][axis], matrix[1][axis], matrix[2][axis]], size)), AXIS_COLORS[axis]); activeCameraCount = output.length / 6; activeCameraVAO = makeLineVAO(new Float32Array(output));
}

const pitchLimit = Math.PI / 2 - .015; let target = [0, 0, 0], yaw = 0, pitch = 0, distance = 5, eye = [0, -5, 0], worldUp = [0, 0, 1], orbitNorth = [0, 1, 0], orbitEast = [1, 0, 0];
let dirtySort = true, lastInteraction = -1e9, cameraMode = 'free', currentCamera = null, selectedCamera = null, activeTool = 'select', axisConstraint = null, drag = null, transformDrag = null;
function moved() { dirtySort = true; lastInteraction = performance.now(); }
function setMode(mode) { cameraMode = mode; document.querySelector('#viewMode').textContent = mode === 'camera' ? 'CAMERA VIEW' : 'FREE VIEW'; }
function freeView() { setMode('free'); currentCamera = null; moved(); }
function setOrbitFromPose(position, forward, focus) { const f = norm(forward), vertical = Math.max(-1, Math.min(1, dot(f, worldUp))), horizontal = sub(f, mul(worldUp, vertical)); pitch = Math.max(-pitchLimit, Math.min(pitchLimit, Math.asin(vertical))); if (dot(horizontal, horizontal) > 1e-10) { const h = norm(horizontal); yaw = Math.atan2(dot(h, orbitEast), dot(h, orbitNorth)); } distance = Math.max(focus, .01); target = add(position, mul(f, distance)); }
function reset() {
  if (!meta) return; freeView(); const corners = []; for (const x of [meta.bounds_min[0], meta.bounds_max[0]]) for (const y of [meta.bounds_min[1], meta.bounds_max[1]]) for (const z of [meta.bounds_min[2], meta.bounds_max[2]]) corners.push(transformPoint(sceneRoot, [x, y, z]));
  const low = [0, 1, 2].map(axis => Math.min(...corners.map(point => point[axis]))), high = [0, 1, 2].map(axis => Math.max(...corners.map(point => point[axis]))); target = mul(add(low, high), .5); distance = Math.max(Math.hypot(...sub(high, low)) * 1.35, .1); yaw = 0; pitch = -.28; moved();
}
function setCameraByImageId(imageId) { if (!meta || !meta.cameras) return false; const record = meta.cameras.find(item => item.colmap_image_id === imageId || item.image_id === imageId); if (!record) return false; const matrix = record.cam2world, position = transformPoint(sceneRoot, [matrix[0][3], matrix[1][3], matrix[2][3]]), forward = transformDirection(sceneRoot, [matrix[0][2], matrix[1][2], matrix[2][2]]); setOrbitFromPose(position, forward, Math.max(meta.initial_focus_distance || 1, .01)); selectedCamera = record; currentCamera = record; setMode('camera'); highlightCamera(record); moved(); document.title = 'camera|' + imageId; return true; }
function camera() { const cp = Math.cos(pitch), f = norm(add(add(mul(orbitNorth, cp * Math.cos(yaw)), mul(orbitEast, cp * Math.sin(yaw))), mul(worldUp, Math.sin(pitch)))); eye = sub(target, mul(f, distance)); const r = norm(cross(f, worldUp)), u = norm(cross(r, f)); return {f, r, u, view: new Float32Array([r[0], u[0], -f[0], 0, r[1], u[1], -f[1], 0, r[2], u[2], -f[2], 0, -dot(r, eye), -dot(u, eye), dot(f, eye), 1])}; }
function perspective(aspect) { const f = 1 / Math.tan(Math.PI / 6), near = .001, far = Math.max(distance * 100, 100); return new Float32Array([f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) / (near - far), -1, 0, 0, 2 * far * near / (near - far), 0]); }
function cameraProjection(record) { const k = record.intrinsics, w = record.width, h = record.height, near = .001, far = Math.max(distance * 100, 100); return new Float32Array([2 * k[0][0] / w, 0, 0, 0, 0, 2 * k[1][1] / h, 0, 0, 1 - 2 * k[0][2] / w, 2 * k[1][2] / h - 1, (far + near) / (near - far), -1, 0, 0, 2 * far * near / (near - far), 0]); }
function renderView(w, h) { if (cameraMode !== 'camera' || !currentCamera) return {x: 0, y: 0, w, h, proj: perspective(w / h)}; const aspect = currentCamera.width / currentCamera.height; let vw = w, vh = Math.round(w / aspect); if (vh > h) { vh = h; vw = Math.round(h * aspect); } return {x: Math.floor((w - vw) / 2), y: Math.floor((h - vh) / 2), w: vw, h: vh, proj: cameraProjection(currentCamera)}; }
function snapView(code) { const axis = code[0], positive = code[1] === '+', index = {X: 0, Y: 1, Z: 2}[axis], from = [0, 0, 0]; from[index] = positive ? 1 : -1; const forward = mul(from, -1); setOrbitFromPose(sub(target, mul(forward, distance)), forward, distance); freeView(); }

function backgroundRgb() { const hex = appearance.background.replace('#', ''); const value = hex.length === 3 ? hex.split('').map(v => v + v).join('') : hex.padEnd(6, '0').slice(0, 6); return [parseInt(value.slice(0, 2), 16) / 255, parseInt(value.slice(2, 4), 16) / 255, parseInt(value.slice(4, 6), 16) / 255]; }
function rebuildWorldReferences() {
  const spacing = Math.pow(10, Math.floor(Math.log10(Math.max(distance, .01))) - 1); if (spacing === gridSpacing && gridVAO) return; gridSpacing = spacing;
  const extent = spacing * 50, light = backgroundRgb().reduce((sum, value) => sum + value, 0) / 3 > .55, minor = light ? [.70, .70, .70] : [.28, .28, .28], major = light ? [.54, .54, .54] : [.40, .40, .40], grid = [];
  for (let i = -50; i <= 50; i++) { if (i === 0) continue; const color = i % 10 === 0 ? major : minor, value = i * spacing; pushSegment(grid, [-extent, value, 0], [extent, value, 0], color); pushSegment(grid, [value, -extent, 0], [value, extent, 0], color); }
  gridCount = grid.length / 6; gridVAO = makeLineVAO(new Float32Array(grid)); const axes = []; pushSegment(axes, [-extent, 0, 0], [extent, 0, 0], AXIS_COLORS[0]); pushSegment(axes, [0, -extent, 0], [0, extent, 0], AXIS_COLORS[1]); pushSegment(axes, [0, 0, -extent * .15], [0, 0, extent * .15], AXIS_COLORS[2]); axesCount = axes.length / 6; axesVAO = makeLineVAO(new Float32Array(axes));
}
function rebuildTransformGizmo() {
  const origin = [...placement.translation], size = Math.max(distance * .12, .03), output = [];
  if (activeTool === 'rotate') { for (let axis = 0; axis < 3; axis++) { let previous = null; for (let step = 0; step <= 64; step++) { const angle = step / 64 * Math.PI * 2, p = [...origin]; const a = (axis + 1) % 3, b = (axis + 2) % 3; p[a] += Math.cos(angle) * size; p[b] += Math.sin(angle) * size; if (previous) pushSegment(output, previous, p, AXIS_COLORS[axis]); previous = p; } } }
  else if (activeTool !== 'select') for (let axis = 0; axis < 3; axis++) { const endpoint = [...origin]; endpoint[axis] += size; pushSegment(output, origin, endpoint, AXIS_COLORS[axis]); const wingA = [...endpoint], wingB = [...endpoint]; wingA[(axis + 1) % 3] -= size * .08; wingB[(axis + 2) % 3] -= size * .08; pushSegment(output, endpoint, wingA, AXIS_COLORS[axis]); pushSegment(output, endpoint, wingB, AXIS_COLORS[axis]); }
  gizmoCount = output.length / 6; gizmoVAO = output.length ? makeLineVAO(new Float32Array(output)) : null;
}
function drawLines(vao, vertices, root, view, proj, width = 1) { if (!vao || !vertices) return; gl.useProgram(lineProgram); gl.uniformMatrix4fv(gl.getUniformLocation(lineProgram, 'root'), false, rowsToGL(root)); gl.uniformMatrix4fv(gl.getUniformLocation(lineProgram, 'view'), false, view); gl.uniformMatrix4fv(gl.getUniformLocation(lineProgram, 'proj'), false, proj); gl.bindVertexArray(vao); gl.lineWidth(width); gl.drawArrays(gl.LINES, 0, vertices); gl.lineWidth(1); }
function drawPoints(vao, vertices, root, view, proj) { if (!vao || !vertices) return; const light = backgroundRgb().reduce((sum, value) => sum + value, 0) / 3 > .55, fallback = light ? [.16, .18, .22] : [.82, .84, .88]; gl.useProgram(pointProgram); gl.uniformMatrix4fv(gl.getUniformLocation(pointProgram, 'root'), false, rowsToGL(root)); gl.uniformMatrix4fv(gl.getUniformLocation(pointProgram, 'view'), false, view); gl.uniformMatrix4fv(gl.getUniformLocation(pointProgram, 'proj'), false, proj); gl.uniform1f(gl.getUniformLocation(pointProgram, 'pointSize'), Math.max(2, Math.min(4, devicePixelRatio * 2))); gl.uniform3fv(gl.getUniformLocation(pointProgram, 'fallbackColor'), fallback); gl.bindVertexArray(vao); gl.drawArrays(gl.POINTS, 0, vertices); }
function sortSplats(c, now) {
  if (!dirtySort || !rawMeans || drag || transformDrag || now - lastInteraction < 140) return;
  const f = c.f, local = [sceneRoot[0] * f[0] + sceneRoot[4] * f[1] + sceneRoot[8] * f[2], sceneRoot[1] * f[0] + sceneRoot[5] * f[1] + sceneRoot[9] * f[2], sceneRoot[2] * f[0] + sceneRoot[6] * f[1] + sceneRoot[10] * f[2]];
  sortIds.sort((a, b) => rawMeans[b * 3] * local[0] + rawMeans[b * 3 + 1] * local[1] + rawMeans[b * 3 + 2] * local[2] - rawMeans[a * 3] * local[0] - rawMeans[a * 3 + 1] * local[1] - rawMeans[a * 3 + 2] * local[2]);
  for (let i = 0; i < count; i++) order[i] = sortIds[i]; gl.bindBuffer(gl.ARRAY_BUFFER, orderBuffer); gl.bufferData(gl.ARRAY_BUFFER, order, gl.DYNAMIC_DRAW); dirtySort = false;
}

function project(point, c, proj, width, height) { const v = c.view, x = v[0] * point[0] + v[4] * point[1] + v[8] * point[2] + v[12], y = v[1] * point[0] + v[5] * point[1] + v[9] * point[2] + v[13], z = v[2] * point[0] + v[6] * point[1] + v[10] * point[2] + v[14], w = -z; if (w <= 0) return null; const clipX = proj[0] * x, clipY = proj[5] * y; return [(clipX / w * .5 + .5) * width, (1 - (clipY / w * .5 + .5)) * height]; }
function pointSegmentDistance(p, a, b) { const ab = [b[0] - a[0], b[1] - a[1]], ap = [p[0] - a[0], p[1] - a[1]], length = ab[0] * ab[0] + ab[1] * ab[1] || 1, t = Math.max(0, Math.min(1, (ap[0] * ab[0] + ap[1] * ab[1]) / length)), q = [a[0] + ab[0] * t, a[1] + ab[1] * t]; return Math.hypot(p[0] - q[0], p[1] - q[1]); }
function pickAxis(x, y) { const c = camera(), proj = perspective(canvas.width / canvas.height), origin = [...placement.translation], size = Math.max(distance * .12, .03), screenOrigin = project(origin, c, proj, canvas.clientWidth, canvas.clientHeight); if (!screenOrigin) return null; let best = null, bestDistance = 14; for (let axis = 0; axis < 3; axis++) { const endpoint = [...origin]; endpoint[axis] += size; const screenEnd = project(endpoint, c, proj, canvas.clientWidth, canvas.clientHeight); if (!screenEnd) continue; const d = pointSegmentDistance([x, y], screenOrigin, screenEnd); if (d < bestDistance) { best = {axis, screenOrigin, screenEnd}; bestDistance = d; } } return best; }
function beginTransform(event) { if (activeTool === 'select') return false; const picked = pickAxis(event.offsetX, event.offsetY); if (!picked && axisConstraint === null) return false; const axis = axisConstraint === null ? picked.axis : axisConstraint, origin = picked ? picked.screenOrigin : [event.offsetX, event.offsetY], end = picked ? picked.screenEnd : [origin[0] + (axis === 0 ? 60 : 0), origin[1] - (axis === 2 ? 60 : axis === 1 ? 40 : 0)]; freeView(); transformDrag = {axis, startX: event.clientX, startY: event.clientY, start: clonePlacement(placement), screenAxis: norm([end[0] - origin[0], end[1] - origin[1], 0])}; canvas.setPointerCapture(event.pointerId); return true; }
function updateTransform(event) { if (!transformDrag) return; const deltaPixels = (event.clientX - transformDrag.startX) * transformDrag.screenAxis[0] + (event.clientY - transformDrag.startY) * transformDrag.screenAxis[1], precision = event.shiftKey ? .1 : 1, axis = transformDrag.axis; placement = clonePlacement(transformDrag.start);
  if (activeTool === 'move') placement.translation[axis] += deltaPixels * distance * .002 * precision;
  else if (activeTool === 'rotate') placement.rotation_xyz_degrees[axis] += deltaPixels * .35 * precision;
  else if (activeTool === 'scale') { const factor = Math.exp(deltaPixels * .01 * precision); if (placement.scale_locked) placement.scale_xyz = placement.scale_xyz.map(value => Math.max(.0001, Math.min(10000, value * factor))); else placement.scale_xyz[axis] = Math.max(.0001, Math.min(10000, placement.scale_xyz[axis] * factor)); }
  sceneRoot = composePlacement(placement); dirtySort = true; rebuildTransformGizmo();
}
function commitTransform() { if (!transformDrag) return; transformDrag = null; axisConstraint = null; dirtySort = true; if (viewerBridge && viewerBridge.commitScenePlacement) viewerBridge.commitScenePlacement(JSON.stringify(placement)); }
function cancelTransform() { if (!transformDrag) return; placement = clonePlacement(transformDrag.start); sceneRoot = composePlacement(placement); transformDrag = null; axisConstraint = null; dirtySort = true; rebuildTransformGizmo(); }

const keys = new Set();
canvas.oncontextmenu = event => event.preventDefault();
canvas.onpointerdown = event => { canvas.focus(); if (event.button === 0 && beginTransform(event)) return; freeView(); drag = {x: event.clientX, y: event.clientY, button: event.button}; canvas.setPointerCapture(event.pointerId); moved(); };
canvas.onpointerup = () => { if (transformDrag) commitTransform(); drag = null; moved(); };
canvas.onpointermove = event => { if (transformDrag) { updateTransform(event); return; } if (!drag) return; const dx = event.clientX - drag.x, dy = event.clientY - drag.y; drag.x = event.clientX; drag.y = event.clientY; if (drag.button === 0) { yaw -= dx * .006; pitch = Math.max(-pitchLimit, Math.min(pitchLimit, pitch - dy * .006)); } else { const c = camera(), speed = distance * .0015; target = add(target, add(mul(c.r, -dx * speed), mul(c.u, dy * speed))); } moved(); };
canvas.onwheel = event => { event.preventDefault(); freeView(); distance = Math.max(.01, distance * Math.exp(event.deltaY * .001)); gridSpacing = 0; moved(); };
canvas.onkeydown = event => { if (event.code === 'KeyG') setTool('move'); else if (event.code === 'KeyR') setTool('rotate'); else if (event.code === 'KeyS') setTool('scale'); else if (['KeyX', 'KeyY', 'KeyZ'].includes(event.code)) axisConstraint = {KeyX: 0, KeyY: 1, KeyZ: 2}[event.code]; else if (event.code === 'Escape') cancelTransform(); else if (event.code === 'Enter') commitTransform(); else keys.add(event.code); moved(); };
canvas.onkeyup = event => { keys.delete(event.code); moved(); };

function setTool(tool) { if (!['select', 'move', 'rotate', 'scale'].includes(tool)) return false; if (transformDrag) cancelTransform(); activeTool = tool; axisConstraint = null; rebuildTransformGizmo(); canvas.focus(); return true; }
function setPlacement(value) { placement = clonePlacement(typeof value === 'string' ? JSON.parse(value) : value); sceneRoot = composePlacement(placement); dirtySort = true; rebuildTransformGizmo(); return true; }
function setAppearance(value) {
  const update = {...(value || {})}; if ('showCameras' in update && !('cameraOverlay' in update)) update.cameraOverlay = update.showCameras ? 'all' : 'off'; delete update.showCameras;
  if ('cameraOverlay' in update && !['off', 'selected', 'all'].includes(update.cameraOverlay)) delete update.cameraOverlay;
  Object.assign(appearance, update); if (update.background) { document.documentElement.style.setProperty('--bg', update.background); gridSpacing = 0; }
  for (const [key, id] of [['showGrid', 'showGrid'], ['showAxes', 'showAxes'], ['showCameraPath', 'showPath'], ['showPoints', 'showP']]) document.querySelector('#' + id).checked = !!appearance[key]; document.querySelector('#showC').checked = appearance.cameraOverlay !== 'off'; return {...appearance};
}
for (const [id, key] of [['showGrid', 'showGrid'], ['showAxes', 'showAxes'], ['showPath', 'showCameraPath'], ['showP', 'showPoints']]) document.querySelector('#' + id).onchange = event => appearance[key] = event.target.checked;
document.querySelector('#showC').onchange = event => appearance.cameraOverlay = event.target.checked ? 'selected' : 'off';
document.querySelector('#reset').onclick = reset; document.querySelector('#freeView').onclick = freeView; document.querySelector('#cameraView').onclick = () => selectedCamera ? setCameraByImageId(selectedCamera.colmap_image_id || selectedCamera.image_id) : meta && meta.cameras && meta.cameras.length && setCameraByImageId(meta.cameras[0].colmap_image_id || meta.cameras[0].image_id); document.querySelectorAll('#navGizmo button').forEach(button => button.onclick = () => snapView(button.dataset.view));

let last = performance.now(), frames = 0, fpsAt = last;
function frame(now) {
  requestAnimationFrame(frame); const dt = Math.min((now - last) / 1000, .05); last = now; let c = camera(), speed = distance * dt * .65, movement = [0, 0, 0]; if (keys.has('KeyW')) movement = add(movement, mul(c.f, speed)); if (keys.has('KeyS')) movement = add(movement, mul(c.f, -speed)); if (keys.has('KeyA')) movement = add(movement, mul(c.r, -speed)); if (keys.has('KeyD')) movement = add(movement, mul(c.r, speed)); if (dot(movement, movement) > 0) { target = add(target, movement); moved(); c = camera(); }
  sortSplats(c, now); const dpr = devicePixelRatio, width = Math.max(1, canvas.clientWidth * dpr | 0), height = Math.max(1, canvas.clientHeight * dpr | 0); if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; dirtySort = true; }
  const bg = backgroundRgb(); gl.viewport(0, 0, width, height); gl.clearColor(bg[0], bg[1], bg[2], 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT); const rv = renderView(width, height), proj = rv.proj; gl.viewport(rv.x, rv.y, rv.w, rv.h); rebuildWorldReferences(); rebuildTransformGizmo();
  gl.disable(gl.BLEND); gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL); gl.depthMask(true);
  if (appearance.showGrid) drawLines(gridVAO, gridCount, IDENTITY, c.view, proj); if (appearance.showAxes) drawLines(axesVAO, axesCount, IDENTITY, c.view, proj, 2); if (appearance.showCameraPath) drawLines(cameraPathVAO, cameraPathCount, sceneRoot, c.view, proj); if (appearance.cameraOverlay === 'all') drawLines(cameraVAO, cameraCount, sceneRoot, c.view, proj); if (appearance.cameraOverlay !== 'off') drawLines(activeCameraVAO, activeCameraCount, sceneRoot, c.view, proj, 3); drawLines(gizmoVAO, gizmoCount, IDENTITY, c.view, proj, 3);
  if (pointVAO && appearance.showPoints) drawPoints(pointVAO, pointCount, sceneRoot, c.view, proj);
  if (dataTexture && document.querySelector('#showG').checked) { gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL); gl.depthMask(false); gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA); gl.useProgram(splatProgram); gl.bindVertexArray(splatVAO); gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, dataTexture); gl.uniform1i(gl.getUniformLocation(splatProgram, 'dataTex'), 0); gl.uniform2i(gl.getUniformLocation(splatProgram, 'texSize'), texW, texH); gl.uniformMatrix4fv(gl.getUniformLocation(splatProgram, 'sceneRoot'), false, rowsToGL(sceneRoot)); gl.uniformMatrix4fv(gl.getUniformLocation(splatProgram, 'view'), false, c.view); gl.uniformMatrix4fv(gl.getUniformLocation(splatProgram, 'proj'), false, proj); gl.uniform3fv(gl.getUniformLocation(splatProgram, 'eye'), eye); gl.uniform2f(gl.getUniformLocation(splatProgram, 'viewport'), rv.w, rv.h); gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, count); }
  gl.disable(gl.BLEND); gl.depthMask(true); gl.depthFunc(gl.LESS); gl.enable(gl.DEPTH_TEST);
  frames++; if (now - fpsAt > 500) { document.querySelector('#fps').textContent = Math.round(frames * 1000 / (now - fpsAt)) + ' FPS'; frames = 0; fpsAt = now; }
}

window.viewerScene = {setAppearance, setTool, setPlacement, snapView, state: () => ({placement: clonePlacement(placement), appearance: {...appearance}, tool: activeTool, worldFromScene: [...sceneRoot], coordinateSystem: meta ? meta.target_coordinate_system : null, selectedCameraId: selectedCamera ? (selectedCamera.colmap_image_id || selectedCamera.image_id) : null, renderPassVertices: {gaussians: count, points: appearance.showPoints ? pointCount : 0, grid: appearance.showGrid ? gridCount : 0, axes: appearance.showAxes ? axesCount : 0, cameraPath: appearance.showCameraPath ? cameraPathCount : 0, cameraFrusta: appearance.cameraOverlay === 'all' ? cameraCount + activeCameraCount : appearance.cameraOverlay === 'selected' ? activeCameraCount : 0, gizmo: gizmoCount}, bridgeReady})};
window.viewerCamera = {setCamera: setCameraByImageId, setFreeView: freeView, setCameraView: () => document.querySelector('#cameraView').click(), state: () => ({mode: cameraMode, imageId: currentCamera ? (currentCamera.colmap_image_id || currentCamera.image_id) : null, selectedImageId: selectedCamera ? (selectedCamera.colmap_image_id || selectedCamera.image_id) : null, eye: [...eye], intrinsics: currentCamera ? currentCamera.intrinsics : null, size: currentCamera ? [currentCamera.width, currentCamera.height] : null})};
window.acceptance = {snapshot: () => { const c = camera(); return {target: [...target], yaw, pitch, distance, eye: [...eye], worldUp: [...worldUp], cameraUp: [...c.u], rollDot: dot(c.r, worldUp), scene: window.viewerScene.state()};}, orbit: (x, y) => { yaw += x; pitch = Math.max(-pitchLimit, Math.min(pitchLimit, pitch + y)); moved(); }, pan: (x, y) => { const c = camera(); target = add(target, add(mul(c.r, x), mul(c.u, y))); moved(); }, zoom: scale => { distance = Math.max(.01, distance * scale); moved(); }, walk: amount => { const c = camera(); target = add(target, mul(c.f, amount)); moved(); }, motionTest: (duration = 1500) => { const started = performance.now(), startYaw = yaw; let n = 0; function step(now) { yaw = startYaw + .03 * Math.sin((now - started) * .012); moved(); n++; if (now - started < duration) requestAnimationFrame(step); else { yaw = startYaw; moved(); document.title = 'motion|' + Math.round(n * 1000 / (now - started)); } } requestAnimationFrame(step); }};

function request(url, type = 'arraybuffer') { return new Promise((resolve, reject) => { const xhr = new XMLHttpRequest(); xhr.open('GET', url); xhr.responseType = type; xhr.onload = () => xhr.status === 200 || xhr.status === 0 ? resolve(xhr.response) : reject(Error(url + ' returned ' + xhr.status)); xhr.onerror = () => reject(Error(url + ' is unavailable')); xhr.send(); }); }
async function load() {
  try { meta = JSON.parse(await request('meta.json', 'text')); placement = clonePlacement(meta.scene_placement); sceneRoot = composePlacement(placement); worldUp = [0, 0, 1]; document.querySelector('#artifact').textContent = meta.artifact; document.querySelector('#unit').textContent = 'Z Up · ' + (meta.has_metric_scale ? meta.world_unit : 'scene units'); const [gaussians, points] = await Promise.all([request('scene.ply'), meta.has_pointcloud ? request('points.ply') : null]); parseGaussian(gaussians); if (points) parsePoints(points); buildCameraGeometry(); reset(); document.title = 'ready|' + count; requestAnimationFrame(frame); }
  catch (error) { fail(error.message || String(error)); }
}
load();
try {
  if (window.qt && window.QWebChannel && qt.webChannelTransport)
    new QWebChannel(qt.webChannelTransport, channel => {
      viewerBridge = channel.objects.viewerBridge || null;
      if (viewerBridge && viewerBridge.ping) viewerBridge.ping(result => {
        bridgeReady = result === 'gaussianos-viewer-bridge/v1';
      });
    });
} catch (error) {
  console.warn('Viewer WebChannel unavailable:', error);
}
