/**
 * Optimized PLY file parser for Three.js point clouds.
 * Handles ASCII PLY format with position + optional RGB color.
 * Uses index scanning instead of .split('\n') and decimates large clouds
 * (>100,000 points) to prevent WebGL memory crashes and frame drops.
 */

export function parsePLY(text) {
  if (!text || typeof text !== 'string') return null;

  const headerEndIdx = text.indexOf('end_header');
  if (headerEndIdx === -1) return null;

  // Move past 'end_header' and trailing newline
  let startOfData = headerEndIdx + 10;
  if (text[startOfData] === '\r') startOfData++;
  if (text[startOfData] === '\n') startOfData++;

  const header = text.slice(0, headerEndIdx);
  const vertexMatch = header.match(/element vertex (\d+)/);
  if (!vertexMatch) return null;

  const totalVertices = parseInt(vertexMatch[1], 10);
  if (totalVertices <= 0) return null;

  const hasColor = header.includes('property uchar red');

  // Subsample large point clouds to at most 100,000 points
  const MAX_POINTS = 100000;
  const step = totalVertices > MAX_POINTS ? Math.ceil(totalVertices / MAX_POINTS) : 1;
  const expectedPoints = Math.min(MAX_POINTS, Math.ceil(totalVertices / step));

  const positions = new Float32Array(expectedPoints * 3);
  const colors = hasColor ? new Float32Array(expectedPoints * 3) : null;

  let lineStart = startOfData;
  let parsedCount = 0;
  let lineIdx = 0;
  const textLen = text.length;

  while (lineStart < textLen && parsedCount < expectedPoints) {
    let lineEnd = text.indexOf('\n', lineStart);
    if (lineEnd === -1) lineEnd = textLen;

    if (lineIdx % step === 0) {
      const line = text.slice(lineStart, lineEnd).trim();
      if (line.length > 0) {
        const parts = line.split(/\s+/);
        if (parts.length >= 3) {
          const x = parseFloat(parts[0]);
          const y = parseFloat(parts[1]);
          const z = parseFloat(parts[2]);

          // Filter rogue triangulation outliers (points placed km away)
          if (!isNaN(x) && !isNaN(y) && !isNaN(z) && Math.abs(x) < 3000 && Math.abs(y) < 3000 && Math.abs(z) < 2000) {
            const outIdx = parsedCount * 3;
            positions[outIdx] = x;
            positions[outIdx + 1] = y;
            positions[outIdx + 2] = z;

            if (hasColor && parts.length >= 6) {
              colors[outIdx] = parseInt(parts[3], 10) / 255;
              colors[outIdx + 1] = parseInt(parts[4], 10) / 255;
              colors[outIdx + 2] = parseInt(parts[5], 10) / 255;
            }
            parsedCount++;
          }
        }
      }
    }

    lineIdx++;
    lineStart = lineEnd + 1;
  }

  // Slice down to actual valid points parsed
  const finalPositions = parsedCount === expectedPoints ? positions : positions.slice(0, parsedCount * 3);
  const finalColors = colors ? (parsedCount === expectedPoints ? colors : colors.slice(0, parsedCount * 3)) : null;

  return { positions: finalPositions, colors: finalColors, vertexCount: parsedCount };
}

/**
 * Compute bounding box center and size for camera framing.
 * Rejects extreme ray outliers to keep camera target accurately centered on real assets.
 */
export function computeBounds(positions) {
  if (!positions || positions.length === 0) {
    return { center: [120, 170, -100], size: 400 };
  }

  let minX = Infinity, minY = Infinity, minZ = Infinity;
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  let validCount = 0;

  // Stride through positions
  const step = positions.length > 30000 ? 30 : 3;
  for (let i = 0; i < positions.length; i += step) {
    const x = positions[i];
    const y = positions[i + 1];
    const z = positions[i + 2];
    if (isNaN(x) || isNaN(y) || isNaN(z)) continue;
    // Reject rogue distant outliers
    if (Math.abs(x) > 2500 || Math.abs(y) > 2500 || Math.abs(z) > 1500) continue;

    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
    if (z < minZ) minZ = z;
    if (z > maxZ) maxZ = z;
    validCount++;
  }

  if (validCount === 0 || minX === Infinity) {
    return { center: [120, 170, -100], size: 400 };
  }

  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const cz = (minZ + maxZ) / 2;
  const rawSize = Math.max(maxX - minX, maxY - minY, maxZ - minZ);
  const size = Math.min(Math.max(rawSize, 60), 1200);

  return {
    center: [cx, cy, cz],
    size,
    min: [minX, minY, minZ],
    max: [maxX, maxY, maxZ],
  };
}
