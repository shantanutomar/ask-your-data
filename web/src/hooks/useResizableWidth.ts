import { type KeyboardEvent, type PointerEvent, useCallback, useRef, useState } from "react";

const STORAGE_KEY = "ayd.sidebar_width";
export const SIDEBAR_MIN = 220;
export const SIDEBAR_MAX = 480;
export const SIDEBAR_DEFAULT = 288;
const KEY_STEP = 16;

const clamp = (n: number) => Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, n));

function readStored(): number {
  try {
    const n = Number(localStorage.getItem(STORAGE_KEY));
    return Number.isFinite(n) && n > 0 ? clamp(n) : SIDEBAR_DEFAULT;
  } catch {
    return SIDEBAR_DEFAULT;
  }
}

function persist(width: number) {
  try {
    localStorage.setItem(STORAGE_KEY, String(width));
  } catch {
    // width just won't be remembered
  }
}

/** Width state + props for a draggable vertical divider (pointer drag, arrow keys, double-click reset). */
export function useResizableWidth() {
  const [width, setWidth] = useState(readStored);
  const [dragging, setDragging] = useState(false);
  const startRef = useRef({ x: 0, width: 0 });
  const widthRef = useRef(width);
  widthRef.current = width;

  const onPointerDown = useCallback((e: PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    startRef.current = { x: e.clientX, width: widthRef.current };
    setDragging(true);
  }, []);

  const onPointerMove = useCallback(
    (e: PointerEvent<HTMLDivElement>) => {
      if (!dragging) return;
      setWidth(clamp(startRef.current.width + e.clientX - startRef.current.x));
    },
    [dragging],
  );

  const endDrag = useCallback(() => {
    if (!dragging) return;
    setDragging(false);
    persist(widthRef.current);
  }, [dragging]);

  const onKeyDown = useCallback((e: KeyboardEvent<HTMLDivElement>) => {
    const delta = e.key === "ArrowLeft" ? -KEY_STEP : e.key === "ArrowRight" ? KEY_STEP : 0;
    if (!delta) return;
    e.preventDefault();
    const next = clamp(widthRef.current + delta);
    setWidth(next);
    persist(next);
  }, []);

  const reset = useCallback(() => {
    setWidth(SIDEBAR_DEFAULT);
    persist(SIDEBAR_DEFAULT);
  }, []);

  return {
    width,
    dragging,
    handleProps: {
      onPointerDown,
      onPointerMove,
      onPointerUp: endDrag,
      onPointerCancel: endDrag,
      onKeyDown,
      onDoubleClick: reset,
    },
  };
}
