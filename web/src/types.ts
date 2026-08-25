export type SourceReference = {
  source_id: string;
  kind: "canonical" | "contextual_resource";
  label: string;
  url?: string | null;
};

export type EntityCardBlock = {
  type: "entity_card";
  entity_type: "song" | "show" | "performance";
  entity_id: string;
  title: string;
  subtitle?: string | null;
  details: string[];
  source_id: string;
};

export type ResourceListBlock = {
  type: "resource_list";
  title: string;
  items: Array<{
    resource_id: string;
    title: string;
    resource_type: string;
    source_name: string;
    url: string;
    source_id: string;
  }>;
};

export type MediaLinkBlock = {
  type: "media_link";
  title: string;
  provider: string;
  url: string;
  link_type: string;
  is_official: boolean;
  embed_kind?: "spotify" | "youtube" | null;
  embed_id?: string | null;
};

export type ArrangementBlock = {
  type: "arrangement";
  title: string;
  resource_id: string;
  source_id: string;
  key_signature?: string | null;
  progressions: string[];
};

export type ProvenanceNoteBlock = {
  type: "provenance_note";
  text: string;
  source_ids: string[];
};

export type GapStateBlock = {
  type: "gap_state";
  message: string;
};

export type ExperienceBlock =
  | EntityCardBlock
  | ResourceListBlock
  | MediaLinkBlock
  | ArrangementBlock
  | ProvenanceNoteBlock
  | GapStateBlock;

export type ExperienceResponse = {
  schema_version: "1";
  thread_id: string;
  title: string;
  answer: string;
  conversation: Array<{
    role: "user" | "assistant";
    text: string;
  }>;
  blocks: ExperienceBlock[];
  sources: SourceReference[];
};
