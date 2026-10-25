from __future__ import annotations
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
from enum import Enum


class SeverityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvidenceType(str, Enum):
    FACT = "FACT"                  # Direct, verified telemetry from logs, metrics, or deployments
    ASSUMPTION = "ASSUMPTION"      # Inferred or extrapolated claim by an agent without direct proof
    CONTRADICTION = "CONTRADICTION" # Evidence that disproves a specific hypothesis


class CriticVerdictStatus(str, Enum):
    APPROVED = "APPROVED"                         # Evidence is sufficient, proceed to report
    REQUEST_MORE_EVIDENCE = "REQUEST_MORE_EVIDENCE" # Gaps or unverified assumptions need follow-up
    INCONCLUSIVE = "INCONCLUSIVE"                 # Telemetry missing or conflicting; cannot conclude


class ActionType(str, Enum):
    IMMEDIATE_MITIGATION = "IMMEDIATE_MITIGATION" # E.g., rollback, restart, failover
    LONG_TERM_PREVENTION = "LONG_TERM_PREVENTION" # E.g., increase pool size, add circuit breaker


class IncidentTicket(BaseModel):
    incident_id: str
    title: str
    description: str
    timestamp: str
    affected_service: str
    severity: SeverityLevel = SeverityLevel.HIGH
    initial_symptoms: List[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    id: str                                      # e.g., "EV-1"
    source: str                                  # "logs" | "metrics" | "deployments" | "topology" | "history"
    type: EvidenceType = EvidenceType.FACT
    description: str                             # Plain-English summary of what was observed
    raw_data: Optional[Dict[str, Any]] = None    # Raw tool output payload
    timestamp: Optional[str] = None
    is_fact: bool = True                         # True if verified directly from tool telemetry
    confidence: float = 1.0                      # Calibration score 0.0 to 1.0


class Hypothesis(BaseModel):
    id: str                                      # e.g., "H1"
    title: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)    # Confidence level 0.0 to 1.0
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    contradicting_evidence_ids: List[str] = Field(default_factory=list)
    is_root_cause: bool = False


class InvestigationTask(BaseModel):
    id: str                                      # e.g., "TASK-1"
    assigned_to: Literal["observability", "dependency"]
    description: str
    tool_name: str
    tool_params: Dict[str, Any] = Field(default_factory=dict)
    status: Literal["PENDING", "COMPLETED", "FAILED"] = "PENDING"
    result: Optional[str] = None


class CriticVerdict(BaseModel):
    status: CriticVerdictStatus
    reasoning: str
    identified_assumptions: List[str] = Field(default_factory=list)
    missing_evidence_questions: List[str] = Field(default_factory=list)
    suggested_follow_up_tasks: List[InvestigationTask] = Field(default_factory=list)


class OrchestratorLLMOutput(BaseModel):
    tasks: List[InvestigationTask] = Field(default_factory=list)


class ReasoningLLMOutput(BaseModel):
    hypotheses: List[Hypothesis] = Field(default_factory=list)


class RemediationAction(BaseModel):
    type: ActionType
    description: str
    target_service: str
    priority: Literal["P0", "P1", "P2"] = "P0"


class IncidentReport(BaseModel):
    incident_id: str
    title: str
    executive_summary: str
    conclusion_status: Literal["RESOLVED", "INCONCLUSIVE"]
    probable_root_cause: Optional[str] = None
    confidence_level: float = 0.0
    ranked_hypotheses: List[Hypothesis] = Field(default_factory=list)
    facts: List[EvidenceItem] = Field(default_factory=list)
    assumptions: List[EvidenceItem] = Field(default_factory=list)
    recommended_actions: List[RemediationAction] = Field(default_factory=list)
    investigation_iterations: int = 1
    total_tool_calls: int = 0
    total_tokens_used: int = 0
    wall_clock_seconds: float = 0.0


import operator
from typing_extensions import TypedDict, Annotated


# Shared State dictionary flowing through LangGraph nodes with reducers for parallel branch fan-in
class InvestigationState(TypedDict, total=False):
    incident_ticket: IncidentTicket
    current_iteration: int
    max_iterations: int
    
    # Task Queue
    active_tasks: List[InvestigationTask]
    completed_tasks: Annotated[List[InvestigationTask], operator.add]
    
    # Shared Evidence & Hypothesis store
    evidence_store: Annotated[List[EvidenceItem], operator.add]
    hypotheses: List[Hypothesis]
    
    # Critic review
    critic_verdict: Optional[CriticVerdict]
    
    # Final generated RCA report
    final_report: Optional[IncidentReport]
    
    # Execution metrics (summed across parallel branches)
    total_tokens_used: Annotated[int, operator.add]
    total_tool_calls: Annotated[int, operator.add]
    start_time: float
    end_time: float
    tool_failure_events: Annotated[List[str], operator.add]
