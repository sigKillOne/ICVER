import networkx as nx
import random
import logging

logger = logging.getLogger("icver.ml.graph_fraud")

def detect_circular_inflation(worker_id: str, num_transactions: int) -> bool:
    """
    Simulate a small local graph of UPI transactions around the worker_id
    and detect if there is a high degree of circular inflation (closed-loop cycles).
    
    Since the current UPI schema does not provide sender/receiver IDs, this
    function mathematically simulates a peer-to-peer network for demonstration.
    
    Returns:
        True if significant cyclic volume is detected, False otherwise.
    """
    if num_transactions < 5:
        # Not enough transactions to confidently detect fraud
        return False
        
    G = nx.DiGraph()
    
    # We simulate 3 to 5 peers
    peers = [f"PEER_{i}" for i in range(random.randint(3, 5))]
    nodes = [worker_id] + peers
    
    # Add some random non-cyclic transactions (normal behavior)
    for _ in range(num_transactions):
        u = random.choice(nodes)
        v = random.choice(nodes)
        if u != v:
            if G.has_edge(u, v):
                G[u][v]['weight'] += 1
            else:
                G.add_edge(u, v, weight=1)
                
    # 30% chance to simulate a fraudulent circular inflation scenario
    # In a real system, this would be computed from actual sender/receiver data
    is_fraud_scenario = random.random() < 0.3
    
    if is_fraud_scenario:
        # Inject a cycle: worker -> peer0 -> peer1 -> worker with high volume
        cycle_nodes = [worker_id, peers[0], peers[1]]
        for i in range(len(cycle_nodes)):
            u = cycle_nodes[i]
            v = cycle_nodes[(i + 1) % len(cycle_nodes)]
            # Add high transaction volume
            if G.has_edge(u, v):
                G[u][v]['weight'] += 5
            else:
                G.add_edge(u, v, weight=5)

    # Detect cycles using NetworkX
    try:
        # simple_cycles can be slow for large graphs, but ours is small
        cycles = list(nx.simple_cycles(G))
    except Exception as e:
        logger.error(f"Error detecting cycles: {e}")
        cycles = []
        
    # Analyze cycles
    fraud_score = 0
    worker_involved_cycles = 0
    
    for cycle in cycles:
        if worker_id in cycle:
            worker_involved_cycles += 1
            # Check the weight of the edges in the cycle
            cycle_weight = min([G[cycle[i]][cycle[(i + 1) % len(cycle)]]['weight'] for i in range(len(cycle))])
            fraud_score += cycle_weight
            
    # Heuristic threshold: if the worker is involved in cycles with high collective weight
    if worker_involved_cycles > 0 and fraud_score >= 5:
        logger.warning(f"Circular inflation detected for {worker_id}. Fraud score: {fraud_score}")
        return True
        
    return False
