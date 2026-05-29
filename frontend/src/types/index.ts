export interface SkuFile {
  file_name: string;
  file_url: string;
  file_type_label: string;
}

export interface SkuItem {
  item_code: string;
  item_name: string;
  brand_name: string | null;
  specification: string | null;
  mfg_sku: string | null;
  l1_category_name: string | null;
  l2_category_name: string | null;
  l3_category_name: string | null;
  l4_category_name: string | null;
  attribute_details: string | null;
  files?: SkuFile[];
}

export interface CompetitorItem {
  name: string;
  price: string | null;
  unit: string | null;
  sku: string | null;
  url: string | null;
  delivery: string | null;
  source: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  imageUrl?: string;     // Data URL for display in user bubble
  skuResults?: SkuItem[];
  competitorResults?: CompetitorItem[];
  isStreaming?: boolean;
  thinkingStatus?: string;
  slotClarification?: SlotClarification;
  comparisonDraft?: ComparisonDraft;
  comparisonTask?: ComparisonTask;
}

export interface SlotMissing {
  key: string;
  icon: string;
  question: string;
  options: string[];
}

export interface SlotKnown {
  label: string;
  value: string;
}

export interface SlotClarification {
  summary: string;
  known: SlotKnown[];
  missing: SlotMissing[];
  submitted?: boolean;  // server sets to true after the user has answered
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
}

export interface AuthUser {
  id: number;
  phone: string;
  nickname: string | null;
  user_id: string;     // external id used as user_id in chat/feedback requests
  auth_token: string;
}

export type ComparisonPlatform = "jd" | "zkh";

export type ComparisonDraftStatus =
  | "needs_confirmation"
  | "needs_login"
  | "ready_to_compare"
  | "task_created"
  | "cancelled";

export type ComparisonTaskStatus =
  | "queued"
  | "running"
  | "partial"
  | "done"
  | "failed"
  | "cancelled";

export type ComparisonSubtaskStatus =
  | "queued"
  | "in_progress"
  | "login_required"
  | "done"
  | "timeout"
  | "failed";

export interface CategoryAlternative {
  l1?: string;
  l2?: string;
  l3?: string;
  l4?: string;
  label: string;
}

export interface ComparisonCategory {
  l1?: string;
  l2?: string;
  l3?: string;
  l4?: string;
  confidence: number;
  alternatives?: CategoryAlternative[];
}

export interface SpecificationAttribute {
  name: string;
  value: string;
  unit?: string;
}

export interface ComparisonSpecification {
  productType?: string;
  brand?: string;
  model?: string;
  material?: string;
  size?: string;
  standard?: string;
  attributes: SpecificationAttribute[];
  missing: string[];
}

export interface PurchaseConstraints {
  quantity?: number;
  unit?: string;
  budgetMax?: number;
  deliveryRequiredBy?: string;
  preferredPlatforms: ComparisonPlatform[];
  requireInStock?: boolean;
}

export interface ComparisonSearchTerms {
  jd: string[];
  zkh: string[];
}

export interface ComparisonStructure {
  category: ComparisonCategory;
  specification: ComparisonSpecification;
  purchaseConstraints: PurchaseConstraints;
  searchTerms: ComparisonSearchTerms;
}

export interface ExternalOffer {
  id: string;
  platform: ComparisonPlatform;
  title: string;
  brand?: string;
  specText?: string;
  priceText?: string;
  priceValue?: number;
  currency: "CNY";
  unitText?: string;
  normalizedUnitPrice?: number;
  unitComparable: boolean;
  minOrderQty?: string;
  stockText?: string;
  deliveryText?: string;
  productUrl: string;
  platformSku?: string;
  rawRank: number;
  matchScore: number;
  matchReasons: string[];
}

export interface PlatformStatus {
  platform: ComparisonPlatform;
  loggedIn?: boolean;
  checkedAt?: string;
  message?: string;
}

export interface ExtensionStatus {
  online: boolean;
  deviceName?: string;
  version?: string;
  platforms: PlatformStatus[];
  lastSeenAt?: string;
}

export interface ComparisonDraft {
  id: string;
  sessionId: string;
  rawQuery: string;
  structure: ComparisonStructure;
  selectedPlatforms: ComparisonPlatform[];
  searchTerms: ComparisonSearchTerms;
  platformStatus?: PlatformStatus[] | null;
  status: ComparisonDraftStatus;
  createdAt: number;
  updatedAt: number;
}

export interface ComparisonSubtask {
  id: string;
  platform: ComparisonPlatform;
  status: ComparisonSubtaskStatus;
  searchTerms: string[];
  items: ExternalOffer[];
  error?: { code?: string; message?: string } | null;
  leasedUntil?: number | null;
  createdAt: number;
  updatedAt: number;
}

export interface ComparisonTask {
  id: string;
  draftId: string;
  status: ComparisonTaskStatus;
  createdAt: number;
  completedAt?: number | null;
  subtasks: ComparisonSubtask[];
}
