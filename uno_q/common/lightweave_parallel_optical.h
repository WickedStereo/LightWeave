#ifndef LIGHTWEAVE_PARALLEL_OPTICAL_H
#define LIGHTWEAVE_PARALLEL_OPTICAL_H

namespace LightWeaveParallel {

constexpr int kLaneCount = 3;

inline int slotCount(int frameBytes) {
  return (frameBytes + kLaneCount - 1) / kLaneCount;
}

inline int bitPeriods(int frameBytes) {
  return slotCount(frameBytes) * 8 + 2;
}

inline int laneByteCount(int frameBytes, int lane) {
  if (lane < 0 || lane >= kLaneCount || frameBytes <= lane) return 0;
  return (frameBytes - lane + kLaneCount - 1) / kLaneCount;
}

}  // namespace LightWeaveParallel

#endif
