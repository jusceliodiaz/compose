// Composição 2.5D — WebGL2 / GLSL ES 3.00 (o three insere "#version 300 es" via glslVersion: GLSL3).
// Ordem (CLAUDE.md §4.6): tudo em LINEAR → mix(beauty, shaded, mask) → exposição → tone map → sRGB.
precision highp float;
precision highp int;
precision highp sampler2D;

in vec2 vUv;
out vec4 fragColor;

// --- Passes da câmera ---------------------------------------------------------------
uniform sampler2D u_beauty;      // linear (EXR) — fundo
uniform sampler2D u_diffLight;   // luz difusa sem cor (linear)
uniform sampler2D u_glossy;      // reflexo (linear)
uniform sampler2D u_shadowAO;    // fallback "modo simplificado" (dado, NoColorSpace)
uniform bool      u_hasDiffLight;
uniform vec3      u_fallbackLight; // cor média do beauty (modo simplificado)

uniform sampler2D u_uvHi;        // NEAREST, NoColorSpace
uniform sampler2D u_uvLo;        // NEAREST, NoColorSpace (no modo u8 é ignorado)
uniform int       u_uvMode;      // 0 = u16_hilo, 1 = uv_map 8-bit
uniform vec4      u_uvRange;     // (uMin, vMin, uMax, vMax) em metros

uniform sampler2D u_mask0;       // até 3 slots por arquivo (R, G, B)
uniform sampler2D u_mask1;

// --- Slots (até 3, num único passe) ----------------------------------------------------
uniform int       u_slotCount;
uniform sampler2D u_albedo0;     // sRGB → linear na leitura, REPEAT, mipmaps, anisotropia
uniform sampler2D u_albedo1;
uniform sampler2D u_albedo2;
uniform vec3  u_tint[3];
uniform vec2  u_tiling[3];       // S = 1 / tamanho real (m)
uniform float u_rotation[3];     // radianos
uniform vec2  u_offset[3];       // em tiles
uniform float u_glossKeep[3];
uniform vec3  u_slotSelect[3];   // one-hot do canal na máscara
uniform float u_slotMaskFile[3]; // 0 → u_mask0, 1 → u_mask1
uniform float u_seamThreshold;
uniform float u_albedoPower;     // 1 = passes lineares; p < 1 quando os passes já vêm com tone mapping

// --- LightMix (até 4 grupos, método da razão) ----------------------------------------
uniform int       u_lightCount;
uniform bool      u_lightMixOn;
uniform sampler2D u_lg0;
uniform sampler2D u_lg1;
uniform sampler2D u_lg2;
uniform sampler2D u_lg3;
uniform vec3      u_lightTint[4]; // intensidade × cor(Kelvin), calculado no JS

// --- Saída -------------------------------------------------------------------------------
uniform float u_exposure;
uniform int   u_toneOp;          // 0 standard (clamp), 1 aces, 2 agx
uniform float u_splitX;          // cortina antes/depois: x < splitX mostra o "antes"
uniform int   u_debug;           // 0 normal, 1 UV, 2 máscaras, 3 luz difusa, 4 costuras, 5 albedo (slot 0)

vec2 decodeUV(vec2 p) {
    vec2 q;
    if (u_uvMode == 0) {
        vec2 hi = floor(texture(u_uvHi, p).rg * 255.0 + 0.5);
        vec2 lo = floor(texture(u_uvLo, p).rg * 255.0 + 0.5);
        q = (hi * 256.0 + lo) / 65535.0;
    } else {
        q = texture(u_uvHi, p).rg;
    }
    return mix(u_uvRange.xy, u_uvRange.zw, q);
}

mat2 rot2(float a) {
    float s = sin(a), c = cos(a);
    return mat2(c, s, -s, c);    // column-major → [[c, -s], [s, c]]
}

vec3 linearToSRGB(vec3 c) {
    c = clamp(c, 0.0, 1.0);
    return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}

vec3 tonemapACES(vec3 x) {
    return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0);
}

// AgX — mesma implementação do three.js (Filament / Blender, primárias Rec.2020)
vec3 agxContrast(vec3 x) {
    vec3 x2 = x * x;
    vec3 x4 = x2 * x2;
    return 15.5 * x4 * x2 - 40.14 * x4 * x + 31.96 * x4 - 6.868 * x2 * x + 0.4298 * x2 + 0.1191 * x - 0.00232;
}

vec3 tonemapAgX(vec3 color) {
    const mat3 SRGB_TO_REC2020 = mat3(
        vec3(0.6274, 0.0691, 0.0164), vec3(0.3293, 0.9195, 0.0880), vec3(0.0433, 0.0113, 0.8956));
    const mat3 REC2020_TO_SRGB = mat3(
        vec3(1.6605, -0.1246, -0.0182), vec3(-0.5876, 1.1329, -0.1006), vec3(-0.0728, -0.0083, 1.1187));
    const mat3 INSET = mat3(
        vec3(0.856627153315983, 0.137318972929847, 0.11189821299995),
        vec3(0.0951212405381588, 0.761241990602591, 0.0767994186031903),
        vec3(0.0482516061458583, 0.101439036467562, 0.811302368396859));
    const mat3 OUTSET = mat3(
        vec3(1.1271005818144368, -0.1413297634984383, -0.14132976349843826),
        vec3(-0.11060664309660323, 1.157823702216272, -0.11060664309660294),
        vec3(-0.016493938717834573, -0.016493938717834257, 1.2519364065950405));
    const float minEv = -12.47393;
    const float maxEv = 4.026069;
    color = INSET * (SRGB_TO_REC2020 * color);
    color = clamp((log2(max(color, 1e-10)) - minEv) / (maxEv - minEv), 0.0, 1.0);
    color = OUTSET * agxContrast(color);
    color = pow(max(vec3(0.0), color), vec3(2.2));
    return clamp(REC2020_TO_SRGB * color, 0.0, 1.0);
}

vec3 toneMap(vec3 hdr) {
    vec3 x = hdr * u_exposure;
    if (u_toneOp == 1) return tonemapACES(x);
    if (u_toneOp == 2) return tonemapAgX(x);
    return clamp(x, 0.0, 1.0);
}

float slotMask(int i, vec4 m0, vec4 m1) {
    vec3 m = u_slotMaskFile[i] < 0.5 ? m0.rgb : m1.rgb;
    return dot(m, u_slotSelect[i]);
}

// Amostra o albedo de um slot. As derivadas chegam prontas (calculadas em fluxo uniforme).
vec3 sampleAlbedo(sampler2D albedoTex, int i, vec2 uv, vec2 duvdx, vec2 duvdy) {
    mat2 R = rot2(u_rotation[i]);
    vec2 tuv = R * (uv * u_tiling[i]) + u_offset[i];
    vec2 dx = R * (duvdx * u_tiling[i]);
    vec2 dy = R * (duvdy * u_tiling[i]);
    // costura de UV (ou borda do slot): derivada enorme → zera para não cair no mip mais borrado
    if (max(dot(dx, dx), dot(dy, dy)) > u_seamThreshold) { dx = vec2(0.0); dy = vec2(0.0); }
    // SEM fract(): o wrap REPEAT da textura cuida da repetição
    vec3 a = textureGrad(albedoTex, tuv, dx, dy).rgb * u_tint[i];
    return u_albedoPower == 1.0 ? a : pow(max(a, vec3(0.0)), vec3(u_albedoPower));
}

// Reilumina o material com a luz calculada pelo renderizador offline.
vec3 relight(vec3 albedo, int i, vec3 diffLight, vec3 glossy) {
    if (u_hasDiffLight) return albedo * diffLight + glossy * u_glossKeep[i];
    return albedo * texture(u_shadowAO, vUv).r * u_fallbackLight;
}

void main() {
    vec3 beauty = texture(u_beauty, vUv).rgb;
    vec4 m0 = texture(u_mask0, vUv);
    vec4 m1 = texture(u_mask1, vUv);

    // UV e derivadas fora de qualquer if (derivadas só são definidas em fluxo uniforme)
    vec2 uv = decodeUV(vUv);
    vec2 duvdx = dFdx(uv);
    vec2 duvdy = dFdy(uv);

    if (u_debug == 1) {
        vec2 n = (uv - u_uvRange.xy) / max(u_uvRange.zw - u_uvRange.xy, vec2(1e-6));
        fragColor = vec4(n, max(m0.r, max(m0.g, m0.b)), 1.0);     // valores crus, sem sRGB
        return;
    }
    if (u_debug == 2) { fragColor = vec4(m0.rgb, 1.0); return; }

    if (u_debug == 5) {
        float k = u_slotCount > 0 ? slotMask(0, m0, m1) : 0.0;
        vec3 a = sampleAlbedo(u_albedo0, 0, uv, duvdx, duvdy);
        fragColor = vec4(mix(vec3(0.0), linearToSRGB(a), k), 1.0);
        return;
    }

    vec3 diffLight = texture(u_diffLight, vUv).rgb;
    vec3 glossy = texture(u_glossy, vUv).rgb;

    if (u_debug == 3) { fragColor = vec4(linearToSRGB(toneMap(diffLight)), 1.0); return; }
    if (u_debug == 4) {
        float d = max(dot(duvdx, duvdx), dot(duvdy, duvdy));
        float seam = step(u_seamThreshold, d);
        vec3 base = linearToSRGB(toneMap(beauty)) * 0.35;
        fragColor = vec4(mix(base + vec3(0.0, sqrt(d) * 8.0, 0.0), vec3(1.0, 0.1, 0.3), seam), 1.0);
        return;
    }

    // LightMix: soma ponderada dos grupos; a razão aplica a mudança de luz ao material trocado
    vec3 mixed = beauty;
    if (u_lightMixOn) {
        mixed = vec3(0.0);
        if (u_lightCount > 0) mixed += texture(u_lg0, vUv).rgb * u_lightTint[0];
        if (u_lightCount > 1) mixed += texture(u_lg1, vUv).rgb * u_lightTint[1];
        if (u_lightCount > 2) mixed += texture(u_lg2, vUv).rgb * u_lightTint[2];
        if (u_lightCount > 3) mixed += texture(u_lg3, vUv).rgb * u_lightTint[3];
    }
    vec3 ratio = mixed / max(beauty, vec3(1e-4));

    vec3 hdr = mixed;
    if (u_slotCount > 0) {
        float k = slotMask(0, m0, m1);
        if (k > 0.001) {
            vec3 s = relight(sampleAlbedo(u_albedo0, 0, uv, duvdx, duvdy), 0, diffLight, glossy);
            hdr = mix(hdr, u_lightMixOn ? s * ratio : s, k);
        }
    }
    if (u_slotCount > 1) {
        float k = slotMask(1, m0, m1);
        if (k > 0.001) {
            vec3 s = relight(sampleAlbedo(u_albedo1, 1, uv, duvdx, duvdy), 1, diffLight, glossy);
            hdr = mix(hdr, u_lightMixOn ? s * ratio : s, k);
        }
    }
    if (u_slotCount > 2) {
        float k = slotMask(2, m0, m1);
        if (k > 0.001) {
            vec3 s = relight(sampleAlbedo(u_albedo2, 2, uv, duvdx, duvdy), 2, diffLight, glossy);
            hdr = mix(hdr, u_lightMixOn ? s * ratio : s, k);
        }
    }

    // comparador antes/depois: o "antes" é o render original sem nenhuma alteração
    if (vUv.x < u_splitX) hdr = beauty;

    // Só agora sai do linear: exposição → tone mapping → sRGB
    fragColor = vec4(linearToSRGB(toneMap(hdr)), 1.0);
}
