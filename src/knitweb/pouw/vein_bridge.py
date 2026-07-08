"""Vein bridge: publish contracts and execution proofs to the P2P Fabric.

Provides thin wrappers over FabricNode.weave() + .link() to integrate Vein
contract execution proofs into Pulse's P2P fabric. Contracts and proofs
propagate over existing InventoryRelay + ReconcileSession rails (no new
transport protocol).

Design:
  - publish_contract(node, record) → weave the contract record, announce to peers
  - publish_proof(node, job, proof, contract_cid) → weave the proof record,
    link it to the contract (proof→contract edge), announce to peers
  - Result: node B receives both contract + proof, independently re-executes
    and verifies, decides to accept or slash
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..fabric.web import FabricNode
    from knitweb_vein import ContractProof, SmartContractProcedureJob

__all__ = ["publish_contract", "publish_proof"]


def publish_contract(node: FabricNode, record: dict) -> str:
    """Weave a smart contract record into the Fabric and announce to peers.

    Args:
        node: The local FabricNode
        record: Contract record (SmartContractRecord.to_record())

    Returns:
        The CID of the published contract

    This is idempotent: weaving the same record twice returns the same CID.
    The record is broadcast to peers via InventoryRelay.
    """
    cid = node.weave(record)
    # node.weave() automatically announces to peers via inventory relay
    return cid


def publish_proof(
    node: FabricNode,
    job: SmartContractProcedureJob,
    proof: ContractProof,
    contract_cid: str,
) -> str:
    """Weave a contract execution proof into the Fabric and link to contract.

    Args:
        node: The local FabricNode
        job: The original SmartContractProcedureJob
        proof: The ContractProof (result + signature + digest)
        contract_cid: CID of the contract this proof executes

    Returns:
        The CID of the published proof

    Creates a proof record, weaves it, and links it to the contract:
      proof --[executes]--> contract

    The proof is broadcast to peers, which independently verify and decide
    whether to accept and propagate further.
    """
    # Build a proof record (canonical-serializable)
    proof_record = {
        "kind": "smart-contract-procedure-proof",
        "job_class": "smart-contract-procedure",
        "contract_cid": contract_cid,
        "procedure_name": job.procedure_name,
        "arguments": job.arguments,
        "originator_pub": job.originator_pub,
        "result": proof.result,
        "signature": proof.signature,
        "digest": proof.digest,
    }

    # Weave the proof
    proof_cid = node.weave(proof_record)

    # Link proof → contract (provenance edge)
    node.link(src=proof_cid, dst=contract_cid, rel="executes", weight=1)

    # node.weave() + node.link() automatically announce to peers
    return proof_cid
