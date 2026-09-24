/**
 * PLY file parser for Three.js point clouds.
 * Handles ASCII PLY format with position + optional RGB color.
 */

export function parsePLY(text) {
  const lines = text.split('\n');
  let headerEnd = 0;
  let vertexCount = 0;
  let hasColor = false;
  let properties = [];

  // Parse header
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line === 'end_header') {
      headerEnd = i + 1;
      break;
    }
    if (line.startsWith('element vertex')) {
      vertexCount = parseInt(line.split(' ')[2]);
    }
    if (line.startsWith('property')) {
      const parts = line.split(' ');
      properties.push(parts[parts.length - 1]);
      if (parts[parts.length - 1] === 'red') hasColor = true;
    }
  }

  const positions = new Float32Array(vertexCount * 3);
  const colors = hasColor ? new Float32Array(vertexCount * 3) : null;

  for (let i = 0; i < vertexCount; i++) {
    const lineIdx = headerEnd + i;
    if (lineIdx >= lines.length) break;

    const values = lines[lineIdx].trim().split(/\s+/).map(Number);
    if (values.length < 3) continue;

    positions[i * 3] = values[0];
    positions[i * 3 + 1] = values[1];
    positions[i * 3 + 2] = values[2];

    if (hasColor && values.length >= 6) {
      colors[i * 3] = values[3] / 255;
      colors[i * 3 + 1] = values[4] / 255;
      colors[i * 3 + 2] = values[5] / 255;
    }
  }

  return { positions, colors, vertexCount };
}

/**
 * Compute bounding box center and size for camera framing.
 */
export function computeBounds(positions) {
  if (!positions || positions.length === 0) {
    return { center: [0, 0, 0], size: 10 };
  }

  let minX = Infinity, minY = Infinity, minZ = Infinity;
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;

  for (let i = 0; i < positions.length; i += 3) {
    minX = Math.min(minX, positions[i]);
    minY = Math.min(minY, positions[i + 1]);
    minZ = Math.min(minZ, positions[i + 2]);
    maxX = Math.max(maxX, positions[i]);
    maxY = Math.max(maxY, positions[i + 1]);
    maxZ = Math.max(maxZ, positions[i + 2]);
  }

  return {
    center: [
      (minX + maxX) / 2,
      (minY + maxY) / 2,
      (minZ + maxZ) / 2,
    ],
    size: Math.max(maxX - minX, maxY - minY, maxZ - minZ),
  };
}
