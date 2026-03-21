import { create } from "zustand";
import type { ScanResponse } from "../types";

interface AnalyzeState {
  scanPath: string;
  scanResult: ScanResponse | null;
  isScanning: boolean;
  scanError: string | null;
  jobId: string | null;
  destinationFolder: string;

  setScanPath: (path: string) => void;
  setScanResult: (result: ScanResponse | null) => void;
  setIsScanning: (v: boolean) => void;
  setScanError: (e: string | null) => void;
  setJobId: (id: string | null) => void;
  setDestinationFolder: (folder: string) => void;
  reset: () => void;
}

export const useAnalyzeStore = create<AnalyzeState>((set) => ({
  scanPath: "",
  scanResult: null,
  isScanning: false,
  scanError: null,
  jobId: null,
  destinationFolder: "",

  setScanPath: (scanPath) => set({ scanPath }),
  setScanResult: (scanResult) => set({ scanResult }),
  setIsScanning: (isScanning) => set({ isScanning }),
  setScanError: (scanError) => set({ scanError }),
  setJobId: (jobId) => set({ jobId }),
  setDestinationFolder: (destinationFolder) => set({ destinationFolder }),
  reset: () =>
    set({
      scanResult: null,
      isScanning: false,
      scanError: null,
      jobId: null,
      destinationFolder: "",
    }),
}));
