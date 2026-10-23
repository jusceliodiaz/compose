// Vista de panorama 360°: cada pixel da tela vira um raio, que lê a composição equirretangular
// (já com materiais, luz e tone mapping, em sRGB) renderizada num WebGLRenderTarget.
// Espelho em JS: src/engine/panoramaView.ts (mesma convenção de yaw/pitch).
precision highp float;

in vec2 vUv;
out vec4 fragColor;

uniform sampler2D u_pano;     // composição atual
uniform sampler2D u_before;   // composição "antes" (só usada com a cortina ligada)
uniform float u_yaw;
uniform float u_pitch;
uniform float u_tanHalf;      // tan(fov vertical / 2)
uniform float u_aspect;       // largura / altura da tela
uniform float u_splitX;       // cortina antes/depois em espaço de TELA (0 = desligada)

const float PI = 3.14159265358979;

void main() {
    vec2 ndc = vUv * 2.0 - 1.0;
    vec3 d = vec3(ndc.x * u_tanHalf * u_aspect, ndc.y * u_tanHalf, -1.0);
    float cp = cos(u_pitch), sp = sin(u_pitch);
    d = vec3(d.x, d.y * cp - d.z * sp, d.y * sp + d.z * cp);
    float cy = cos(u_yaw), sy = sin(u_yaw);
    d = vec3(d.x * cy - d.z * sy, d.y, d.x * sy + d.z * cy);
    d = normalize(d);

    vec2 uv = vec2(0.5 + atan(d.x, -d.z) / (2.0 * PI), 0.5 + asin(clamp(d.y, -1.0, 1.0)) / PI);
    // sem mipmaps: o salto de u na emenda (1 → 0) não afeta a filtragem; S em REPEAT fecha a costura
    vec3 c = vUv.x < u_splitX ? texture(u_before, uv).rgb : texture(u_pano, uv).rgb;
    fragColor = vec4(c, 1.0);
}
