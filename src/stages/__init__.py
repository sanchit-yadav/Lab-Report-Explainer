"""Modular, independently testable pipeline stages for AI Clinical Lab Report Explainer."""

from src.stages.explain import ExplainStage, explain
from src.stages.extract import ExtractValuesStage, extract_values
from src.stages.logger import get_stage_logger
from src.stages.ocr import OCRParseStage, ocr_parse
from src.stages.output_guard import OutputGuardStage, output_guard
from src.stages.retrieve import RetrieveStage, retrieve
from src.stages.schemas import (
    ExplainInput,
    ExplainOutput,
    ExtractionOutputItem,
    ExtractValuesInput,
    ExtractValuesOutput,
    OCRLine,
    OCRPage,
    OCRParseInput,
    OCRParseOutput,
    OutputGuardInput,
    OutputGuardOutput,
    RetrievedChunk,
    RetrieveInput,
    RetrieveOutput,
    TestExplanationItem,
    ValidateUploadInput,
    ValidateUploadOutput,
    generate_request_id,
)
from src.stages.validate import ValidateUploadStage, validate_upload

__all__ = [
    # Stages
    "ValidateUploadStage",
    "validate_upload",
    "OCRParseStage",
    "ocr_parse",
    "ExtractValuesStage",
    "extract_values",
    "RetrieveStage",
    "retrieve",
    "ExplainStage",
    "explain",
    "OutputGuardStage",
    "output_guard",
    # Logger
    "get_stage_logger",
    "generate_request_id",
    # Schemas
    "ValidateUploadInput",
    "ValidateUploadOutput",
    "OCRParseInput",
    "OCRParseOutput",
    "OCRPage",
    "OCRLine",
    "ExtractValuesInput",
    "ExtractValuesOutput",
    "ExtractionOutputItem",
    "RetrieveInput",
    "RetrieveOutput",
    "RetrievedChunk",
    "ExplainInput",
    "ExplainOutput",
    "TestExplanationItem",
    "OutputGuardInput",
    "OutputGuardOutput",
]
