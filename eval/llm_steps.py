"""Builds Wajo's brain and classifier for a given eval mode."""

from concurrent.futures import ThreadPoolExecutor

from agent.brain import LLMBrain
from agent.classifier import Classifier
from agent.llm import LLM
from eval.inbox import Case
from eval.stub_llm import StubLLM


def llm_steps(mode: str, cases: list[Case], seed: int, workers: int = 16):
    """mode "stub": offline worst-case stand-in. mode "llm": the LLM in .env, with a response cache.
    Returns (brain, classify)."""
    if mode == "stub":
        stub = StubLLM(cases, seed)
        return stub, stub.classify
    llm = LLM()
    classify = Classifier(llm)
    with ThreadPoolExecutor(workers) as pool:  # fill the classifier cache in parallel
        list(pool.map(classify, [c.email for c in cases if c.incoming]))
    return LLMBrain(llm), classify
