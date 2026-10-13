# ADR 0008 V1 product boundaries

**Status:** Accepted for V1

## Context

The project should demonstrate practical full-stack/backend engineering and focused AI integration while avoiding an unfinished platform with excessive scope.

## Decision

V1 supports Owner and Member, existing registered and verified WorkOS-user membership only, knowledge areas, text-based PDFs without OCR, document upload/search, evidence-based Ask KnowFlow with verbatim page-aware source passages, and no persisted conversation history. Owners manage content and membership; Members can view/download authorized sources and ask/search. Non-empty areas cannot be deleted. V1 uses no generative LLM; see ADR 0011.

## Alternatives

- Add invitations, version comparison, analytics, OCR, history, granular permissions or advanced audit at launch.
- Restrict V1 to one user/workspace.

## Consequences

V1 retains genuine multi-user tenant boundaries and a complete product journey without adding V2/V3 capabilities. Later scope changes require explicit discussion and approval.
