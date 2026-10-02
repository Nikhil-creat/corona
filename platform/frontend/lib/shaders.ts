/** GLSL for the volumetric heat field (floor) and node surfaces. Executed on the GPU every frame —
 *  the heat field is a fragment-shader "compute" pass (sum of gaussian emitters); see README for the WebGPU/TSL upgrade path. */

export const MAX_EMITTERS = 16;

export const fieldVertex = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

export const fieldFragment = /* glsl */ `
precision highp float;
#define MAX_EMITTERS ${MAX_EMITTERS}
uniform vec3 uPts[MAX_EMITTERS];   // x, z (world), heat 0..1
uniform int uCount;
uniform float uSize;
uniform float uTime;
varying vec2 vUv;

vec3 ramp(float t) {
  vec3 a = vec3(0.02, 0.05, 0.12), b = vec3(0.10, 0.45, 0.85), c = vec3(0.98, 0.75, 0.15), d = vec3(0.98, 0.25, 0.20);
  return t < 0.4 ? mix(a, b, t / 0.4) : t < 0.75 ? mix(b, c, (t - 0.4) / 0.35) : mix(c, d, (t - 0.75) / 0.25);
}
void main() {
  vec2 p = (vUv - 0.5) * uSize;
  float field = 0.0;
  for (int i = 0; i < MAX_EMITTERS; i++) {
    if (i >= uCount) break;
    float d = distance(p, uPts[i].xy);
    field += uPts[i].z * exp(-d * d / 14.0);
  }
  field = clamp(field, 0.0, 1.0);
  float grid = step(0.97, fract(p.x * 0.5)) + step(0.97, fract(p.y * 0.5));
  float ripple = 0.04 * sin(length(p) * 0.8 - uTime * 1.5) * field;
  vec3 col = ramp(clamp(field + ripple, 0.0, 1.0)) + vec3(0.04, 0.08, 0.14) * grid;
  float fade = smoothstep(0.5, 0.2, length(vUv - 0.5));
  gl_FragColor = vec4(col, (0.25 + 0.65 * field) * fade);
}`;

export const nodeVertex = /* glsl */ `
varying vec3 vN; varying vec3 vV; varying vec3 vP;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vN = normalize(normalMatrix * normal);
  vV = normalize(-mv.xyz);
  vP = position;
  gl_Position = projectionMatrix * mv;
}`;

export const nodeFragment = /* glsl */ `
precision highp float;
uniform float uHeat; uniform float uPulse; uniform float uTime; uniform vec3 uStatus;
varying vec3 vN; varying vec3 vV; varying vec3 vP;
vec3 ramp(float t) {
  vec3 b = vec3(0.10, 0.45, 0.85), c = vec3(0.98, 0.75, 0.15), d = vec3(0.98, 0.25, 0.20);
  return t < 0.5 ? mix(b, c, t / 0.5) : mix(c, d, (t - 0.5) / 0.5);
}
void main() {
  float fres = pow(1.0 - max(dot(normalize(vN), normalize(vV)), 0.0), 2.5);
  float scan = 0.5 + 0.5 * sin(vP.y * 9.0 - uTime * 3.0);
  vec3 base = mix(vec3(0.05, 0.08, 0.14), ramp(uHeat), 0.35 + 0.65 * uHeat);
  vec3 col = base * (0.7 + 0.3 * scan) + uStatus * fres * (0.8 + 0.8 * uPulse);
  gl_FragColor = vec4(col, 1.0);
}`;
