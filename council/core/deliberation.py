"""Multi-round deliberation for Model Council.

This module implements the deliberation process where models:
1. Round 1: Review independently
2. Round 2+: Read others' opinions and re-evaluate
3. Final: Consolidate into unified verdict
"""

import asyncio
from dataclasses import dataclass
from typing import Optional
import time

from council.core.models import get_model_client, ModelResponse
from council.core.voting import aggregate_results, Verdict
from council.db.storage import CouncilStorage, RoundOpinion
from council.tasks.base import BaseTask, TaskResult


@dataclass
class DeliberationConfig:
    """Configuration for deliberation process."""
    rounds: int = 2
    max_rounds: int = 5
    storage_enabled: bool = True
    early_stop_on_consensus: bool = True  # Stop if all agree


@dataclass
class DeliberationResult:
    """Result of a deliberation session."""
    session_id: str
    verdict: Verdict
    total_rounds: int
    opinion_changes: list[dict]
    stats: dict


class Deliberation:
    """Orchestrates multi-round model deliberation."""
    
    def __init__(
        self,
        task: BaseTask,
        models: list[str],
        config: Optional[DeliberationConfig] = None,
        storage: Optional[CouncilStorage] = None,
    ):
        """Initialize deliberation.
        
        Args:
            task: The task being performed (pr-review, architecture, etc.)
            models: List of model names to use
            config: Deliberation configuration
            storage: Storage instance (created if not provided)
        """
        self.task = task
        self.models = models
        self.config = config or DeliberationConfig()
        self.storage = storage if self.config.storage_enabled else None
        
        if self.config.storage_enabled and not self.storage:
            self.storage = CouncilStorage()
        
        # Validate rounds
        if self.config.rounds > self.config.max_rounds:
            self.config.rounds = self.config.max_rounds
    
    async def run(self, input_data: dict) -> DeliberationResult:
        """Run the full deliberation process.
        
        Args:
            input_data: Task input data (from task.fetch_input)
            
        Returns:
            DeliberationResult with verdict and metadata
        """
        # Create source and session in storage
        source_id = None
        session_id = None
        
        if self.storage:
            source = self.storage.create_source(
                task_type=self.task.name,
                source_ref=input_data.get("url") or input_data.get("source", "unknown"),
                scope=self._extract_scope(input_data),
                title=input_data.get("title"),
                raw_content=input_data.get("diff") or input_data.get("content"),
                metadata={k: v for k, v in input_data.items() 
                         if k not in ("diff", "content", "raw_content")},
            )
            source_id = source.id
            
            session = self.storage.create_session(
                source_id=source_id,
                models=self.models,
                max_rounds=self.config.rounds,
            )
            session_id = session.id
        else:
            session_id = "no-storage"
        
        # Track all opinions by round
        all_opinions: dict[int, list[TaskResult]] = {}
        opinion_changes: list[dict] = []
        
        # Run deliberation rounds
        for round_num in range(1, self.config.rounds + 1):
            # Get previous round opinions (for round 2+)
            prev_opinions = all_opinions.get(round_num - 1, [])
            
            # Run this round
            round_results = await self._run_round(
                input_data=input_data,
                round_number=round_num,
                session_id=session_id,
                previous_opinions=prev_opinions,
            )
            
            all_opinions[round_num] = round_results
            
            # Track opinion changes (round 2+)
            if round_num > 1 and prev_opinions:
                changes = self._detect_opinion_changes(
                    session_id=session_id,
                    prev_opinions=prev_opinions,
                    curr_opinions=round_results,
                    round_from=round_num - 1,
                    round_to=round_num,
                )
                opinion_changes.extend(changes)
            
            # Check for early stop (full consensus)
            if self.config.early_stop_on_consensus and round_num < self.config.rounds:
                verdicts = [r.decision for r in round_results if not r.error]
                if verdicts and len(set(verdicts)) == 1:
                    # All models agree, no need to continue
                    break
        
        # Get final round results
        final_round = max(all_opinions.keys())
        final_results = all_opinions[final_round]
        
        # Consolidate verdict
        verdict = self._consolidate(final_results)
        
        # Get stats and save verdict
        stats = {}
        if self.storage:
            stats = self.storage.get_session_stats(session_id)
            
            self.storage.save_verdict(
                session_id=session_id,
                source_id=source_id,
                consolidator_model=self.models[0],
                final_score=verdict.score,
                final_verdict=verdict.decision,
                consensus_level=verdict.consensus,
                summary=verdict.summary,
                issues=verdict.issues,
                total_rounds=final_round,
            )
            
            self.storage.complete_session(session_id)
        
        return DeliberationResult(
            session_id=session_id,
            verdict=verdict,
            total_rounds=final_round,
            opinion_changes=opinion_changes,
            stats=stats,
        )
    
    async def _run_round(
        self,
        input_data: dict,
        round_number: int,
        session_id: str,
        previous_opinions: list[TaskResult],
    ) -> list[TaskResult]:
        """Run a single deliberation round.
        
        Args:
            input_data: Task input data
            round_number: Current round (1-indexed)
            session_id: Session ID for storage
            previous_opinions: Opinions from previous round (empty for round 1)
            
        Returns:
            List of TaskResult from each model
        """
        # Create round in storage
        round_id = None
        if self.storage:
            round_id = self.storage.create_round(session_id, round_number)
        
        # Build prompts
        system_prompt, user_prompt = self.task.build_prompt(input_data)
        
        # For round 2+, inject previous opinions
        if round_number > 1 and previous_opinions:
            opinions_context = self._format_opinions_for_context(previous_opinions)
            user_prompt = self._inject_opinions_context(
                user_prompt, opinions_context, round_number
            )
        
        # Run all models in parallel
        async def run_model(model_name: str) -> TaskResult:
            start_time = time.time()
            
            try:
                client = get_model_client(model_name)
                response = await client.generate(system_prompt, user_prompt)
                
                latency_ms = int((time.time() - start_time) * 1000)
                
                if response.error:
                    result = TaskResult.from_error(model_name, response.error)
                else:
                    result = self.task.parse_response(model_name, response.content)
                
                # Record observation
                if self.storage:
                    self.storage.record_observation(
                        session_id=session_id,
                        model=model_name,
                        action="review" if round_number == 1 else "re-review",
                        round_number=round_number,
                        latency_ms=latency_ms,
                        error=result.error,
                    )
                    
                    # Save opinion
                    self.storage.save_opinion(
                        round_id=round_id,
                        session_id=session_id,
                        round_number=round_number,
                        model=model_name,
                        score=result.score,
                        verdict=result.decision,
                        summary=result.summary,
                        issues=result.issues,
                        extras=result.extras,
                        raw_response=response.content if not response.error else None,
                    )
                
                return result
                
            except Exception as e:
                result = TaskResult.from_error(model_name, str(e))
                
                if self.storage:
                    self.storage.record_observation(
                        session_id=session_id,
                        model=model_name,
                        action="review" if round_number == 1 else "re-review",
                        round_number=round_number,
                        error=str(e),
                    )
                
                return result
        
        # Run all models concurrently
        results = await asyncio.gather(*[run_model(m) for m in self.models])
        
        # Complete round
        if self.storage and round_id:
            self.storage.complete_round(round_id)
        
        return list(results)
    
    def _format_opinions_for_context(self, opinions: list[TaskResult]) -> str:
        """Format previous opinions for injection into prompt."""
        lines = ["## Previous Round Opinions\n"]
        
        for op in opinions:
            if op.error:
                lines.append(f"**{op.model_name}**: [Error] {op.error}\n")
            else:
                verdict_emoji = {
                    "APPROVE": "✅",
                    "REQUEST_CHANGES": "🔴",
                    "COMMENT": "💬",
                }.get(op.decision, "❓")
                
                lines.append(f"**{op.model_name}** ({op.score:.0%}) {verdict_emoji} {op.decision}")
                lines.append(f"> {op.summary}\n")
                
                if op.issues:
                    lines.append("Key issues raised:")
                    for issue in op.issues[:3]:  # Limit to top 3
                        lines.append(f"- [{issue.get('severity', 'minor')}] {issue.get('description', '')[:100]}")
                    lines.append("")
        
        return "\n".join(lines)
    
    def _inject_opinions_context(
        self, 
        user_prompt: str, 
        opinions_context: str,
        round_number: int,
    ) -> str:
        """Inject previous opinions into the user prompt."""
        round_instruction = f"""
---

{opinions_context}

---

## Round {round_number} Instructions

You have seen the opinions of other reviewers above. Now provide YOUR updated assessment.

Consider:
- Points raised by others that you may have missed
- Whether you agree or disagree with their assessments
- If you change your opinion, briefly explain why in your summary

Respond with the same JSON format as before. Your score and verdict may change based on the discussion.
"""
        
        return user_prompt + round_instruction
    
    def _detect_opinion_changes(
        self,
        session_id: str,
        prev_opinions: list[TaskResult],
        curr_opinions: list[TaskResult],
        round_from: int,
        round_to: int,
    ) -> list[dict]:
        """Detect and record changes in opinions between rounds."""
        changes = []
        
        # Build lookup for previous opinions
        prev_by_model = {op.model_name: op for op in prev_opinions}
        
        for curr in curr_opinions:
            prev = prev_by_model.get(curr.model_name)
            
            if not prev or prev.error or curr.error:
                continue
            
            # Check if anything changed
            score_changed = abs((prev.score or 0) - (curr.score or 0)) > 0.05
            verdict_changed = prev.decision != curr.decision
            
            if score_changed or verdict_changed:
                change = {
                    "model": curr.model_name,
                    "round_from": round_from,
                    "round_to": round_to,
                    "score_before": prev.score,
                    "score_after": curr.score,
                    "verdict_before": prev.decision,
                    "verdict_after": curr.decision,
                }
                changes.append(change)
                
                # Record in storage
                if self.storage:
                    self.storage.record_opinion_change(
                        session_id=session_id,
                        model=curr.model_name,
                        round_from=round_from,
                        round_to=round_to,
                        score_before=prev.score,
                        score_after=curr.score,
                        verdict_before=prev.decision,
                        verdict_after=curr.decision,
                    )
        
        return changes
    
    def _consolidate(self, results: list[TaskResult]) -> Verdict:
        """Consolidate final results into a verdict."""
        return aggregate_results(results)
    
    def _extract_scope(self, input_data: dict) -> Optional[str]:
        """Extract scope (e.g., owner/repo) from input data."""
        # Try URL parsing
        url = input_data.get("url", "")
        if "github.com" in url:
            parts = url.split("github.com/")[-1].split("/")
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
        
        # Try explicit fields
        if "owner" in input_data and "repo" in input_data:
            return f"{input_data['owner']}/{input_data['repo']}"
        
        return input_data.get("scope")


async def run_deliberation(
    task: BaseTask,
    input_data: dict,
    models: list[str],
    rounds: int = 2,
    storage_enabled: bool = True,
) -> DeliberationResult:
    """Convenience function to run deliberation.
    
    Args:
        task: Task to run
        input_data: Task input data
        models: Models to use
        rounds: Number of deliberation rounds
        storage_enabled: Whether to persist to database
        
    Returns:
        DeliberationResult
    """
    config = DeliberationConfig(
        rounds=rounds,
        storage_enabled=storage_enabled,
    )
    
    deliberation = Deliberation(task, models, config)
    return await deliberation.run(input_data)
