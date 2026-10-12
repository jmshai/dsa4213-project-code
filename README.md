# DSA4213 Project -- Agent Memory: What is used and What isn't?

## Goal of the Project

Looking beyond the retrieval capabilities of agents, we aim to explore if
agents are able to recognise the context and apply the correct memory given
the presence of both a standing and a scoped preference. 

We will evaluate this behaviour by utilising 40 episodes to check for 
over-application or under-application of scoped memories. We will then compare
the results against existing memory solutions like Supermemory and Mem0. 

## Problem

### Hypothesis
Explicit scope representation and scope-aware conflict resolution will
improve agents' adherence to scoped instructions while preserving 
standing preferences in their own intended scope. 

We further hypothesise that some failures might occur even with correct memory
retrieval, revealing a gap between successful retrieval and the desired
action selection downstream.

### Success
Able to show that this gap exists and that a scope-tagged memory layer is able
to improve correction adherence without hurting unrelated-memory retention,
and pinpointing whether failures occur due to extraction, retrieval, or
incorrect agent reasoning.

