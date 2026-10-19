// Quad em tela cheia: PlaneGeometry(1, 1) → vértices em ±0.5, levados direto ao clip space.
in vec3 position;
in vec2 uv;
out vec2 vUv;

void main() {
    vUv = uv;
    gl_Position = vec4(position.xy * 2.0, 0.0, 1.0);
}
