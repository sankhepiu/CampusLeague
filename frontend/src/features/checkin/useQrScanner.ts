import { useEffect, useRef, useState } from 'react';
import jsQR from 'jsqr';

type CameraState = 'idle' | 'starting' | 'running' | 'denied' | 'unavailable';

/** Drives a <video> off the device camera and decodes QR codes from it via
 * jsQR, frame by frame on a canvas. Falls back cleanly (CameraState 'denied'
 * or 'unavailable') so the caller can always offer manual code entry instead. */
export function useQrScanner(onDecode: (text: string) => void, enabled: boolean) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const frameRef = useRef<number | null>(null);
  const onDecodeRef = useRef(onDecode);

  useEffect(() => {
    onDecodeRef.current = onDecode;
  }, [onDecode]);

  // Camera-API support is a static fact for the session, so it's a lazy
  // initializer rather than something the effect below needs to set.
  const hasCameraApi = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia;
  const [cameraState, setCameraState] = useState<CameraState>(hasCameraApi ? 'idle' : 'unavailable');

  useEffect(() => {
    if (!enabled || !hasCameraApi) return;

    let cancelled = false;
    setCameraState('starting');

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: 'environment' } })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        const video = videoRef.current;
        if (!video) return;
        video.srcObject = stream;
        video.play().catch(() => {});
        setCameraState('running');

        if (!canvasRef.current) canvasRef.current = document.createElement('canvas');
        const canvas = canvasRef.current;
        const ctx = canvas.getContext('2d', { willReadFrequently: true });

        const tick = () => {
          if (cancelled) return;
          if (video.readyState === video.HAVE_ENOUGH_DATA && ctx) {
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            const frame = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const result = jsQR(frame.data, frame.width, frame.height);
            if (result?.data) onDecodeRef.current(result.data);
          }
          frameRef.current = requestAnimationFrame(tick);
        };
        frameRef.current = requestAnimationFrame(tick);
      })
      .catch(() => {
        if (!cancelled) setCameraState('denied');
      });

    return () => {
      cancelled = true;
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, [enabled, hasCameraApi]);

  return { videoRef, cameraState };
}
