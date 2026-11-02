"""Operations script to delete all data and media files for a business (GDPR/privacy wipe)."""

import argparse
import logging
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.logging_utils import mask_phone
from app.models.base import SessionLocal
from app.models.entities import Business, Campaign, MediaAsset

logger = logging.getLogger(__name__)


def delete_business_data(
    db: Session,
    phone_e164: str | None = None,
    business_id: int | None = None,
) -> dict[str, Any]:
    """Delete all files and database records for a business.

    Returns summary of deleted assets.
    """
    if not phone_e164 and not business_id:
        raise ValueError("Must provide either phone_e164 or business_id")

    query = db.query(Business)
    if business_id:
        query = query.filter(Business.id == business_id)
    if phone_e164:
        query = query.filter(Business.phone_e164 == phone_e164)

    business = query.first()
    if not business:
        return {"found": False, "deleted": False}

    biz_id = business.id
    phone = business.phone_e164

    # 1. Collect files to delete
    campaigns = db.query(Campaign).filter(Campaign.business_id == biz_id).all()
    campaign_ids = [c.id for c in campaigns]

    assets = db.query(MediaAsset).filter(MediaAsset.business_id == biz_id).all()
    asset_paths = [Path(a.path) for a in assets if a.path]

    deleted_files = 0
    deleted_dirs = 0

    # Delete campaign directories
    for cid in campaign_ids:
        camp_dir = Path(f"data/campaigns/{cid}")
        if camp_dir.exists() and camp_dir.is_dir():
            shutil.rmtree(camp_dir, ignore_errors=True)
            deleted_dirs += 1

    # Delete any lingering asset paths
    for p in asset_paths:
        if p.exists() and p.is_file():
            try:
                p.unlink()
                deleted_files += 1
            except OSError:
                pass

    # 2. Delete database records
    from app.models.entities import (
        CampaignStep,
        Conversation,
        CostLog,
        MenuItem,
        Message,
        UsageCounter,
        Video,
    )

    if campaign_ids:
        db.query(CostLog).filter(CostLog.campaign_id.in_(campaign_ids)).delete(synchronize_session=False)
        db.query(CampaignStep).filter(CampaignStep.campaign_id.in_(campaign_ids)).delete(synchronize_session=False)
        db.query(Video).filter(Video.campaign_id.in_(campaign_ids)).delete(synchronize_session=False)
        db.query(Campaign).filter(Campaign.business_id == biz_id).delete(synchronize_session=False)

    db.query(MediaAsset).filter(MediaAsset.business_id == biz_id).delete(synchronize_session=False)
    db.query(MenuItem).filter(MenuItem.business_id == biz_id).delete(synchronize_session=False)
    db.query(UsageCounter).filter(UsageCounter.business_id == biz_id).delete(synchronize_session=False)

    convs = db.query(Conversation).filter(Conversation.business_id == biz_id).all()
    for conv in convs:
        db.query(Message).filter(Message.conversation_id == conv.id).delete(synchronize_session=False)
        db.delete(conv)

    db.delete(business)
    db.commit()

    return {
        "found": True,
        "deleted": True,
        "business_id": biz_id,
        "phone_masked": mask_phone(phone),
        "campaigns_count": len(campaign_ids),
        "deleted_dirs": deleted_dirs,
        "deleted_files": deleted_files,
    }


def main() -> None:
    """CLI entrypoint for business wipeout."""
    parser = argparse.ArgumentParser(description="Purge all business records and files from Reelwala.")
    parser.add_argument("--phone", type=str, help="Business phone in E.164 format (+91...)")
    parser.add_argument("--id", type=int, help="Business database ID")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    if not args.phone and not args.id:
        parser.error("Must provide either --phone or --id")

    identifier = args.phone or f"ID #{args.id}"
    if not args.force:
        confirm = input(f"Are you sure you want to completely delete business {identifier} and all its data? (yes/no): ")
        if confirm.strip().lower() not in ("yes", "y"):
            print("Aborted.")
            return

    db = SessionLocal()
    try:
        res = delete_business_data(db, phone_e164=args.phone, business_id=args.id)
        if not res["found"]:
            print(f"Business {identifier} not found.")
        else:
            print(f"Successfully deleted business {res['phone_masked']} (ID {res['business_id']}):")
            print(f"- {res['campaigns_count']} campaigns purged")
            print(f"- {res['deleted_dirs']} directories removed")
            print(f"- {res['deleted_files']} media files unlinked")
    finally:
        db.close()


if __name__ == "__main__":
    main()
