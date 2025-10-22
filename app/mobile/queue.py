from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4


@dataclass
class MobileQueueItem:
    queue_id: str
    filename: str
    stored_path: Path
    metadata: Dict[str, Any]
    status: str
    queued_at: float

    @property
    def thumbnail_candidate(self) -> Path:
        return self.stored_path.parent / "thumbnail.jpg"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.queue_id,
            "filename": self.filename,
            "metadata": self.metadata,
            "status": self.status,
            "queued_at": self.queued_at,
            "stored_path": str(self.stored_path),
        }


class MobileUploadQueueManager:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        root = Path(base_dir or Path("artifacts") / "mobile_queue")
        self.base_dir = root
        self.pending_dir = self.base_dir / "pending"
        self.processed_dir = self.base_dir / "processed"
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def enqueue(self, filename: str, data: bytes, metadata: Dict[str, Any], queued_at: float) -> MobileQueueItem:
        queue_id = uuid4().hex
        item_dir = self.pending_dir / queue_id
        item_dir.mkdir(parents=True, exist_ok=True)
        extension = Path(filename).suffix or ".jpg"
        stored_path = item_dir / f"upload{extension}"
        stored_path.write_bytes(data)
        metadata_path = item_dir / "metadata.json"
        metadata_payload = {
            "metadata": metadata,
            "original_filename": filename,
            "queued_at": queued_at,
        }
        metadata_path.write_text(json.dumps(metadata_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return MobileQueueItem(
            queue_id=queue_id,
            filename=filename,
            stored_path=stored_path,
            metadata=metadata,
            status="pending",
            queued_at=queued_at,
        )

    def snapshot(self, *, include_processed: bool = False) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        items.extend(self._load_items(self.pending_dir, status="pending"))
        if include_processed:
            items.extend(self._load_items(self.processed_dir, status="processed"))
        return items

    def get_item(self, queue_id: str, *, include_processed: bool = False) -> Optional[MobileQueueItem]:
        pending_path = self.pending_dir / queue_id
        if pending_path.exists():
            return self._build_item_from_dir(pending_path)
        if include_processed:
            processed_path = self.processed_dir / queue_id
            if processed_path.exists():
                return self._build_item_from_dir(processed_path)
        return None

    def update_metadata(self, queue_id: str, updates: Dict[str, Any], *, processed: bool = False) -> None:
        base_dir = self.processed_dir if processed else self.pending_dir
        item_dir = base_dir / queue_id
        if not item_dir.exists():
            raise FileNotFoundError(f"Queue item {queue_id} not found")
        metadata_path = item_dir / "metadata.json"
        payload: Dict[str, Any]
        if metadata_path.exists():
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        else:
            payload = {}
        payload.update(updates)
        metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def store_analysis(self, queue_id: str, analysis_payload: Dict[str, Any]) -> None:
        self.update_metadata(
            queue_id,
            {
                "analysis": analysis_payload,
                "status": "awaiting_confirmation",
            },
            processed=False,
        )

    def get_metadata(self, queue_id: str, *, processed: bool = False) -> Dict[str, Any]:
        base_dir = self.processed_dir if processed else self.pending_dir
        item_dir = base_dir / queue_id
        if not item_dir.exists():
            raise FileNotFoundError(f"Queue item {queue_id} not found")
        metadata_path = item_dir / "metadata.json"
        if not metadata_path.exists():
            return {}
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def pop_next(self) -> Optional[MobileQueueItem]:
        pending_items = sorted(self.pending_dir.iterdir(), key=lambda path: path.stat().st_ctime)
        if not pending_items:
            return None
        item_dir = pending_items[0]
        metadata_path = item_dir / "metadata.json"
        metadata_payload = metadata_path.read_text(encoding="utf-8") if metadata_path.exists() else "{}"
        payload = json.loads(metadata_payload)
        stored_files = [p for p in item_dir.iterdir() if p.name != "metadata.json"]
        file_path = stored_files[0] if stored_files else item_dir / "upload.bin"
        if not file_path.exists():
            return None
        return MobileQueueItem(
            queue_id=item_dir.name,
            filename=payload.get("original_filename", file_path.name),
            stored_path=file_path,
            metadata=payload.get("metadata", {}),
            status="pending",
            queued_at=payload.get("queued_at", file_path.stat().st_ctime),
        )

    def _load_items(self, directory: Path, *, status: str) -> Iterable[Dict[str, Any]]:
        for item_dir in directory.iterdir():
            if not item_dir.is_dir():
                continue
            metadata_path = item_dir / "metadata.json"
            payload: Dict[str, Any]
            if metadata_path.exists():
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            else:
                payload = {}
            stored_files = [p for p in item_dir.iterdir() if p.name != "metadata.json"]
            file_path = stored_files[0] if stored_files else item_dir / "upload.bin"
            yield {
                "id": item_dir.name,
                "filename": payload.get("original_filename", file_path.name),
                "metadata": payload.get("metadata", {}),
                "status": payload.get("status", status),
                "queued_at": payload.get("queued_at", file_path.stat().st_ctime),
                "stored_path": str(file_path),
                "processed_at": payload.get("processed_at"),
                "result_summary": payload.get("result_summary"),
                "analysis": payload.get("analysis"),
            }

    def _build_item_from_dir(self, item_dir: Path) -> Optional[MobileQueueItem]:
        metadata_path = item_dir / "metadata.json"
        if not metadata_path.exists():
            return None
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        stored_files = [p for p in item_dir.iterdir() if p.name != "metadata.json"]
        file_path = stored_files[0] if stored_files else item_dir / "upload.bin"
        if not file_path.exists():
            return None
        return MobileQueueItem(
            queue_id=item_dir.name,
            filename=payload.get("original_filename", file_path.name),
            stored_path=file_path,
            metadata=payload.get("metadata", {}),
            status=payload.get("status", "pending"),
            queued_at=payload.get("queued_at", file_path.stat().st_ctime),
        )

    def mark_processed(
        self,
        item: MobileQueueItem,
        *,
        status: str = "processed",
        result_summary: Optional[Dict[str, Any]] = None,
    ) -> None:
        source_dir = item.stored_path.parent
        target_dir = self.processed_dir / item.queue_id
        target_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = source_dir / "metadata.json"
        metadata_payload: Dict[str, Any]
        if metadata_path.exists():
            metadata_payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        else:
            metadata_payload = {}
        metadata_payload["status"] = status
        metadata_payload["processed_at"] = datetime.now().timestamp()
        if result_summary is not None:
            metadata_payload["result_summary"] = result_summary
        (target_dir / "metadata.json").write_text(
            json.dumps(metadata_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # move upload file
        stored_files = [p for p in source_dir.iterdir() if p.name != "metadata.json"]
        for path in stored_files:
            target_path = target_dir / path.name
            target_path.write_bytes(path.read_bytes())
        # cleanup source directory
        for path in source_dir.iterdir():
            if path.is_file():
                path.unlink()
        source_dir.rmdir()