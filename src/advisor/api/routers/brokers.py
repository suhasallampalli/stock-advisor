"""Per-user broker credentials — stored Fernet-encrypted, never returned in clear."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..crypto import decrypt_json, encrypt_json
from ..db import get_db
from ..deps import get_current_user
from ..models_db import BrokerCredential, User
from ..schemas import BrokerCredIn, BrokerCredOut

router = APIRouter(prefix="/brokers", tags=["brokers"])

# field name -> required?
BROKER_FIELDS: dict[str, dict[str, bool]] = {
    "zerodha": {"api_key": True, "api_secret": True, "access_token": False},
    "upstox": {"api_key": True, "api_secret": True, "redirect_uri": False, "access_token": False},
    "angelone": {"api_key": True, "client_id": True, "mpin": True, "totp_secret": True},
}
_SECRET_LIKE = ("secret", "token", "mpin", "password", "pin")


def _mask(field: str, value: str) -> str:
    if any(k in field.lower() for k in _SECRET_LIKE):
        return ("*" * max(0, len(value) - 4)) + value[-4:] if value else ""
    return value


def _to_out(cred: BrokerCredential) -> BrokerCredOut:
    data = decrypt_json(cred.enc_payload)
    return BrokerCredOut(
        broker=cred.broker,
        fields_set=sorted(data.keys()),
        masked={k: _mask(k, str(v)) for k, v in data.items()},
        updated_at=cred.updated_at,
    )


@router.get("", response_model=list[BrokerCredOut])
def list_brokers(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[BrokerCredOut]:
    rows = db.scalars(select(BrokerCredential).where(BrokerCredential.user_id == user.id)).all()
    return [_to_out(r) for r in rows]


@router.put("/{broker}", response_model=BrokerCredOut)
def upsert_broker(
    body: BrokerCredIn,
    broker: str = Path(pattern="^(zerodha|upstox|angelone)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BrokerCredOut:
    spec = BROKER_FIELDS[broker]
    unknown = set(body.fields) - set(spec)
    if unknown:
        raise HTTPException(422, f"Unknown fields for {broker}: {sorted(unknown)}")
    missing = [f for f, req in spec.items() if req and not body.fields.get(f)]
    if missing:
        raise HTTPException(422, f"Missing required fields: {missing}")

    payload = {k: v for k, v in body.fields.items() if v != ""}
    cred = db.scalar(
        select(BrokerCredential).where(
            BrokerCredential.user_id == user.id, BrokerCredential.broker == broker
        )
    )
    if cred is None:
        cred = BrokerCredential(user_id=user.id, broker=broker)
        db.add(cred)
    cred.enc_payload = encrypt_json(payload)
    cred.field_names = ",".join(sorted(payload))
    db.commit()
    db.refresh(cred)
    return _to_out(cred)


@router.delete("/{broker}", status_code=status.HTTP_204_NO_CONTENT)
def delete_broker(
    broker: str = Path(pattern="^(zerodha|upstox|angelone)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    cred = db.scalar(
        select(BrokerCredential).where(
            BrokerCredential.user_id == user.id, BrokerCredential.broker == broker
        )
    )
    if cred is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not configured")
    db.delete(cred)
    db.commit()
