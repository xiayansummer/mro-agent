from enum import StrEnum
from typing import Literal, Optional

from pydantic import BaseModel, Field


Platform = Literal["jd", "zkh"]


class ComparisonDraftStatus(StrEnum):
    NEEDS_CONFIRMATION = "needs_confirmation"
    NEEDS_LOGIN = "needs_login"
    READY_TO_COMPARE = "ready_to_compare"
    TASK_CREATED = "task_created"
    CANCELLED = "cancelled"


class ComparisonTaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PARTIAL = "partial"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ComparisonSubtaskStatus(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    LOGIN_REQUIRED = "login_required"
    DONE = "done"
    TIMEOUT = "timeout"
    FAILED = "failed"


class CategoryAlternative(BaseModel):
    l1: Optional[str] = None
    l2: Optional[str] = None
    l3: Optional[str] = None
    l4: Optional[str] = None
    label: str


class ComparisonCategory(BaseModel):
    l1: Optional[str] = None
    l2: Optional[str] = None
    l3: Optional[str] = None
    l4: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    alternatives: list[CategoryAlternative] = Field(default_factory=list)


class SpecificationAttribute(BaseModel):
    name: str
    value: str
    unit: Optional[str] = None


class ComparisonSpecification(BaseModel):
    productType: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    material: Optional[str] = None
    size: Optional[str] = None
    standard: Optional[str] = None
    attributes: list[SpecificationAttribute] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class PurchaseConstraints(BaseModel):
    quantity: Optional[float] = None
    unit: Optional[str] = None
    budgetMax: Optional[float] = None
    deliveryRequiredBy: Optional[str] = None
    preferredPlatforms: list[Platform] = Field(default_factory=lambda: ["jd", "zkh"])
    requireInStock: Optional[bool] = None


class ComparisonSearchTerms(BaseModel):
    jd: list[str] = Field(default_factory=list)
    zkh: list[str] = Field(default_factory=list)


class ComparisonStructure(BaseModel):
    category: ComparisonCategory = Field(default_factory=ComparisonCategory)
    specification: ComparisonSpecification = Field(default_factory=ComparisonSpecification)
    purchaseConstraints: PurchaseConstraints = Field(default_factory=PurchaseConstraints)
    searchTerms: ComparisonSearchTerms = Field(default_factory=ComparisonSearchTerms)


class ExternalOffer(BaseModel):
    id: str
    platform: Platform
    title: str
    brand: Optional[str] = None
    specText: Optional[str] = None
    priceText: Optional[str] = None
    priceValue: Optional[float] = None
    currency: Literal["CNY"] = "CNY"
    unitText: Optional[str] = None
    normalizedUnitPrice: Optional[float] = None
    unitComparable: bool
    minOrderQty: Optional[str] = None
    stockText: Optional[str] = None
    deliveryText: Optional[str] = None
    productUrl: str
    platformSku: Optional[str] = None
    imageUrl: Optional[str] = None
    rawRank: int
    matchScore: float = Field(ge=0.0)
    matchReasons: list[str] = Field(default_factory=list)


class PlatformStatus(BaseModel):
    platform: Platform
    loggedIn: Optional[bool] = None
    checkedAt: Optional[str] = None
    message: Optional[str] = None


class ExtensionStatus(BaseModel):
    online: bool = False
    deviceName: Optional[str] = None
    version: Optional[str] = None
    platforms: list[PlatformStatus] = Field(default_factory=list)
    lastSeenAt: Optional[str] = None
