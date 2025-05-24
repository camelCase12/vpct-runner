from dataclasses import dataclass, field
from typing import Optional, List

@dataclass(slots=True)
class PredictionResult:
    simulation_id: int
    initial_image_path: str
    prompt: str
    model_response: str
    actual_bucket: int
    predicted_bucket: Optional[int]
    is_correct: bool


@dataclass(slots=True)
class BenchmarkResult:
    model_name: str
    predictions: List[PredictionResult] = field(default_factory=list)

    @property
    def overall_accuracy(self) -> float:
        if not self.predictions:
            return 0.0
        return sum(p.is_correct for p in self.predictions) / len(self.predictions)
