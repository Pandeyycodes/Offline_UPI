from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from typing import Optional
import concurrent.futures

from models.db import get_db, Account, Transaction
from models.schemas import MeshPacket, SendRequest, IngestResponse
from crypto.key_holder import ServerKeyHolder
from services.bridge_ingestion import BridgeIngestionService
from services.mesh_simulator import MeshSimulatorService
from services.demo_service import simulate_send
from services.idempotency import IdempotencyService

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/api/server-key")
def server_key():
    return {"public_key": ServerKeyHolder.get().public_key_b64()}


@router.get("/api/accounts")
def accounts(db: Session = Depends(get_db)):
    rows = db.execute(select(Account)).scalars().all()
    return [
        {"vpa": a.vpa, "name": a.name, "balance": round(a.balance, 2)}
        for a in rows
    ]


@router.get("/api/transactions")
def transactions(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Transaction).order_by(desc(Transaction.settled_at)).limit(20)
    ).scalars().all()
    return [
        {
            "id": t.id,
            "sender_vpa": t.sender_vpa,
            "receiver_vpa": t.receiver_vpa,
            "amount": t.amount,
            "settled_at": t.settled_at.isoformat() if t.settled_at else None,
            "bridge_node_id": t.bridge_node_id,
            "hop_count": t.hop_count,
            "packet_hash": t.packet_hash[:16] + "...",
        }
        for t in rows
    ]


@router.get("/api/mesh/state")
def mesh_state():
    return MeshSimulatorService.get().state()


@router.post("/api/demo/send")
def demo_send(req: SendRequest, db: Session = Depends(get_db)):
    packet = simulate_send(req)
    mesh_state = MeshSimulatorService.get().state()
    return {
        "packet_id": packet.packet_id,
        "ttl": packet.ttl,
        "mesh_state": mesh_state,
    }


@router.post("/api/mesh/gossip")
def gossip():
    mesh = MeshSimulatorService.get()
    mesh.gossip_round()
    return {"mesh_state": mesh.state()}


@router.post("/api/mesh/flush")
def flush_bridges(db: Session = Depends(get_db)):
    mesh = MeshSimulatorService.get()
    bridges = mesh.get_bridge_devices()
    results = []

    def upload_from_bridge(bridge):
        bridge_results = []
        for packet in bridge.get_packets():
            from models.db import SessionLocal
            bridge_db = SessionLocal()
            try:
                resp = BridgeIngestionService.ingest(
                    packet=packet,
                    db=bridge_db,
                    bridge_node_id=bridge.device_id,
                    hop_count=5 - packet.ttl,
                )
                bridge_results.append({
                    "bridge": bridge.device_id,
                    "packet_id": packet.packet_id,
                    "outcome": resp.outcome,
                    "transaction_id": resp.transaction_id,
                    "reason": resp.reason,
                })
            finally:
                bridge_db.close()
        return bridge_results

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(upload_from_bridge, b) for b in bridges]
        for f in concurrent.futures.as_completed(futures):
            results.extend(f.result())

    return {"results": results, "mesh_state": mesh.state()}


@router.post("/api/mesh/reset")
def reset_mesh():
    MeshSimulatorService.get().reset()
    IdempotencyService.get().reset()
    return {"status": "reset", "mesh_state": MeshSimulatorService.get().state()}


@router.post("/api/bridge/ingest", response_model=IngestResponse)
def bridge_ingest(
    packet: MeshPacket,
    db: Session = Depends(get_db),
    x_bridge_node_id: Optional[str] = Header(default="unknown"),
    x_hop_count: Optional[int] = Header(default=0),
):
    return BridgeIngestionService.ingest(
        packet=packet,
        db=db,
        bridge_node_id=x_bridge_node_id,
        hop_count=x_hop_count,
    )
