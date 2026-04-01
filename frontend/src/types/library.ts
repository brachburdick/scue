/** Library page types. */

export type LibraryTab = "rekordbox" | "hardware" | "audio" | "scue_library";

export type ImportMode = "metadata" | "metadata_analysis";

export interface LibraryFilterState {
  search: string;
  sourceFilter: "all" | "rekordbox" | "hardware" | "audio";
  tierFilter: {
    has_quick?: boolean;
    has_standard?: boolean;
    has_deep?: boolean;
    has_live?: boolean;
    has_live_offline?: boolean;
  };
}
