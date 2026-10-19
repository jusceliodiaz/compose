import * as THREE from 'three';

const canvas = document.querySelector<HTMLCanvasElement>('#view')!;
const renderer = new THREE.WebGLRenderer({ canvas });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight, false);
renderer.setClearColor(0x000000, 1);
renderer.clear();
