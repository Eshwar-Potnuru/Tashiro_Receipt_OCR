"""Scaffolding for multi-receipt batch processing.

TODO: Replace placeholder batch iteration with production-safe orchestration when green-lit.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from app.history.submission_history import SubmissionHistory
from app.utils.logging_utils import log_batch_event, log_batch_file_event


class MultiReceiptPipeline:
	"""Sequential multi-receipt processor (placeholder implementation)."""

	def __init__(self, engine: str, submission_history: SubmissionHistory):
		self.engine = engine
		self.submission_history = submission_history
		self.logger = logging.getLogger(__name__)

	def process_batch(self, batch_id: str, files: List[str]) -> None:
		"""Sequentially process files with placeholder behavior."""

		# TODO: integrate queueing/backpressure once real OCR wiring is added.
		self.logger.info("Starting batch %s with %s files", batch_id, len(files))
		self.submission_history.update_batch_status(batch_id, 'processing')
		log_batch_event({
			'batch_id': batch_id,
			'engine': self.engine,
			'file_count': len(files),
			'status': 'processing'
		})

		for file_path in files:
			filename = Path(file_path).name
			self.submission_history.update_file_status(batch_id, filename, 'processing')
			log_batch_file_event({
				'batch_id': batch_id,
				'filename': filename,
				'status': 'processing'
			})

			# Placeholder stub – no real OCR yet.
			result = self.process_single(file_path)
			self.logger.debug("Batch %s placeholder result for %s: %s", batch_id, filename, result)

			self.submission_history.update_file_status(batch_id, filename, 'completed')
			log_batch_file_event({
				'batch_id': batch_id,
				'filename': filename,
				'status': 'completed'
			})

		self.submission_history.update_batch_status(batch_id, 'completed')
		log_batch_event({
			'batch_id': batch_id,
			'engine': self.engine,
			'file_count': len(files),
			'status': 'completed'
		})
		self.logger.info("Completed batch %s", batch_id)

	def process_single(self, file_path: str) -> dict:
		"""Placeholder single-file handler for future OCR integration."""

		# TODO: integrate image preprocessing + OCR engines (Document AI + standard stack).
		# TODO: invoke merge logic + verification once available.
		# TODO: add Excel/export hooks after multi-receipt MVP.
		# TODO: surface validation + summarization outputs.
		self.logger.info("Received placeholder file %s for engine %s", file_path, self.engine)
		return {
			'file_path': file_path,
			'engine': self.engine,
			'status': 'pending_ocr'
		}
