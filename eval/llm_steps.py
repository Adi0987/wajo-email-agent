"""Builds the two LLM steps (propose, classify) for a given mode."""
from concurrent.futures import ThreadPoolExecutor

from agent.classifier import Classifier
from agent.llm import LLM
from agent.mailbox import Mailbox
from agent.proposer import Proposer
from eval.inbox import USER, Case
from eval.stub_llm import StubLLM


def llm_steps(mode: str, cases: list[Case], seed: int, workers: int = 16):
    """mode "stub": offline worst-case stand-in. mode "deepseek": real LLM with cache."""
    if mode == "stub":
        stub = StubLLM(cases, seed)
        return stub.propose, stub.classify
    llm = LLM()
    propose, classify = Proposer(llm), Classifier(llm)
    mailbox = Mailbox(USER)
    incoming = [c.email for c in cases if c.incoming]
    with ThreadPoolExecutor(workers) as pool:   # fill the cache in parallel
        list(pool.map(classify, incoming))
        list(pool.map(lambda email: propose(email, mailbox), incoming))   # cold start, no usual choice
    return propose, classify
