from typing import Optional
from pathlib import Path

DEFAULT_PROMPT = """
You are an expert physics simulator. Looking at this image of a ball-and-bucket physics simulation, predict which bucket (numbered 1, 2, or 3 from left to right) the ball will eventually fall into.

Let's think about this step by step:

1. First, observe the initial position of the ball
2. Note any obstacles or lines drawn that will affect the ball's path
3. Consider how gravity will affect the ball's trajectory
4. Think about how the ball will bounce and roll along the surfaces
5. Analyze how the placement and angle of each line will guide the ball
6. Factor in that the ball has some elasticity and will bounce slightly when it hits surfaces

Based on your analysis, please conclude with a clear answer in this format: 'answer(X)' where X is the bucket number (1, 2, or 3).

Explain your reasoning, then end with your answer in the specified format.
""".strip()

def load_prompt(path: Optional[Path]) -> str:
    if path is None:
        return DEFAULT_PROMPT
    return path.read_text().strip()