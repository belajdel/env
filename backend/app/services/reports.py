"""
Report Generation Service
CSV (pandas) and PDF (ReportLab) export for measurements, alerts, and AI reports.
"""

import asyncio
import io
import csv
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, BinaryIO
from pathlib import Path

import pandas as pd
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, 
    PageBreak, KeepTogether
)
from reportlab.platypus.flowables import HRFlowable

from app.core.config import settings
from app.core.database import get_database, Collections
from app.core.logging import get_logger
from app.models.report import ReportInDB, ReportPublic, ReportCreate, ReportType, ReportFormat
from app.models.measurement import MeasurementInDB
from app.models.alert import AlertInDB
from app.services.audit import get_audit_service

logger = get_logger(__name__)


class ReportService:
    """Report generation and management service."""
    
    def __init__(self):
        self.report_dir = Path(settings.REPORT_DIR) if hasattr(settings, 'REPORT_DIR') else Path("/app/reports")
        self.report_dir.mkdir(parents=True, exist_ok=True)
    
    async def create_report(self, report_create: ReportCreate, user_id: str) -> ReportPublic:
        """Create a new report generation job."""
        db = get_database()
        
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=30)  # Reports expire after 30 days
        
        report = ReportInDB(
            **report_create.model_dump(),
            generated_by=user_id,
            status="pending",
            generated_at=now,
            expires_at=expires_at,
        )
        
        result = await db[Collections.REPORTS].insert_one(report.model_dump(by_alias=True))
        report.id = result.inserted_id
        
        # Start generation in background
        asyncio.create_task(self._generate_report(str(report.id)))
        
        logger.info("report_created", report_id=str(report.id), type=report_create.report_type, user=user_id)
        return ReportPublic.from_db(report)
    
    async def _generate_report(self, report_id: str) -> None:
        """Background task to generate report."""
        db = get_database()
        from bson import ObjectId
        
        try:
            # Update status to generating
            await db[Collections.REPORTS].update_one(
                {"_id": ObjectId(report_id)},
                {"$set": {"status": "generating"}}
            )
            
            report_doc = await db[Collections.REPORTS].find_one({"_id": ObjectId(report_id)})
            if not report_doc:
                return
            
            report = ReportInDB(**report_doc)
            
            # Generate based on type
            if report.report_type == ReportType.HOURLY:
                content = await self._generate_hourly_report(report)
            elif report.report_type == ReportType.DAILY:
                content = await self._generate_daily_report(report)
            elif report.report_type == ReportType.WEEKLY:
                content = await self._generate_weekly_report(report)
            elif report.report_type == ReportType.MONTHLY:
                content = await self._generate_monthly_report(report)
            elif report.report_type == ReportType.CUSTOM:
                content = await self._generate_custom_report(report)
            elif report.report_type == ReportType.ALERT_SUMMARY:
                content = await self._generate_alert_summary_report(report)
            elif report.report_type == ReportType.AI_WEEKLY:
                content = await self._generate_ai_weekly_report(report)
            else:
                raise ValueError(f"Unknown report type: {report.report_type}")
            
            # Save file
            filename = f"{report_id}.{report.format}"
            filepath = self.report_dir / filename
            
            if report.format == ReportFormat.CSV:
                await self._save_csv(content, filepath)
            elif report.format == ReportFormat.PDF:
                await self._save_pdf(content, report, filepath)
            elif report.format == ReportFormat.JSON:
                await self._save_json(content, filepath)
            
            # Update report record
            file_size = filepath.stat().st_size
            row_count = len(content) if isinstance(content, list) else (len(content.get("data", [])) if isinstance(content, dict) else 0)
            
            await db[Collections.REPORTS].update_one(
                {"_id": ObjectId(report_id)},
                {"$set": {
                    "status": "completed",
                    "file_path": str(filepath),
                    "file_size": file_size,
                    "row_count": row_count,
                    "completed_at": datetime.now(timezone.utc),
                }}
            )
            
            logger.info("report_generated", report_id=report_id, file_size=file_size, rows=row_count)
            
        except Exception as e:
            logger.error("report_generation_failed", report_id=report_id, error=str(e))
            await db[Collections.REPORTS].update_one(
                {"_id": ObjectId(report_id)},
                {"$set": {
                    "status": "failed",
                    "error_message": str(e),
                    "completed_at": datetime.now(timezone.utc),
                }}
            )
    
    # ============================================
    # Report Generators
    # ============================================
    
    async def _generate_hourly_report(self, report: ReportInDB) -> List[Dict]:
        """Generate hourly measurement report."""
        db = get_database()
        
        cursor = db[Collections.MEASUREMENTS_1MIN].find({
            "metadata.zone_id": report.zone_id,
            "timestamp": {"$gte": report.start, "$lte": report.end},
        }).sort("timestamp", 1)
        
        if report.parameters:
            cursor = cursor.find({"metadata.parameter": {"$in": report.parameters}})
        
        data = []
        async for doc in cursor:
            data.append({
                "timestamp": doc["timestamp"].isoformat(),
                "zone_id": doc["metadata"]["zone_id"],
                "parameter": doc["metadata"]["parameter"],
                "count": doc["count"],
                "min": doc["min"],
                "max": doc["max"],
                "avg": doc["avg"],
                "std": doc.get("std"),
                "unit": doc["unit"],
            })
        
        return data
    
    async def _generate_daily_report(self, report: ReportInDB) -> List[Dict]:
        """Generate daily aggregated report."""
        db = get_database()
        
        # Aggregate hourly data into daily
        pipeline = [
            {"$match": {
                "metadata.zone_id": report.zone_id,
                "timestamp": {"$gte": report.start, "$lte": report.end},
            }},
            {"$group": {
                "_id": {
                    "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                    "parameter": "$metadata.parameter",
                },
                "count": {"$sum": "$count"},
                "min": {"$min": "$min"},
                "max": {"$max": "$max"},
                "avg": {"$avg": "$avg"},
                "unit": {"$first": "$unit"},
            }},
            {"$sort": {"_id.date": 1, "_id.parameter": 1}},
        ]
        
        if report.parameters:
            pipeline[0]["$match"]["metadata.parameter"] = {"$in": report.parameters}
        
        data = []
        async for doc in db[Collections.MEASUREMENTS_1MIN].aggregate(pipeline):
            data.append({
                "date": doc["_id"]["date"],
                "parameter": doc["_id"]["parameter"],
                "count": doc["count"],
                "min": doc["min"],
                "max": doc["max"],
                "avg": round(doc["avg"], 2),
                "unit": doc["unit"],
            })
        
        return data
    
    async def _generate_weekly_report(self, report: ReportInDB) -> List[Dict]:
        """Generate weekly aggregated report."""
        db = get_database()
        
        pipeline = [
            {"$match": {
                "metadata.zone_id": report.zone_id,
                "timestamp": {"$gte": report.start, "$lte": report.end},
            }},
            {"$group": {
                "_id": {
                    "week": {"$dateToString": {"format": "%Y-W%U", "date": "$timestamp"}},
                    "parameter": "$metadata.parameter",
                },
                "count": {"$sum": "$count"},
                "min": {"$min": "$min"},
                "max": {"$max": "$max"},
                "avg": {"$avg": "$avg"},
                "unit": {"$first": "$unit"},
            }},
            {"$sort": {"_id.week": 1, "_id.parameter": 1}},
        ]
        
        if report.parameters:
            pipeline[0]["$match"]["metadata.parameter"] = {"$in": report.parameters}
        
        data = []
        async for doc in db[Collections.MEASUREMENTS_1MIN].aggregate(pipeline):
            data.append({
                "week": doc["_id"]["week"],
                "parameter": doc["_id"]["parameter"],
                "count": doc["count"],
                "min": doc["min"],
                "max": doc["max"],
                "avg": round(doc["avg"], 2),
                "unit": doc["unit"],
            })
        
        return data
    
    async def _generate_monthly_report(self, report: ReportInDB) -> List[Dict]:
        """Generate monthly aggregated report."""
        db = get_database()
        
        pipeline = [
            {"$match": {
                "metadata.zone_id": report.zone_id,
                "timestamp": {"$gte": report.start, "$lte": report.end},
            }},
            {"$group": {
                "_id": {
                    "month": {"$dateToString": {"format": "%Y-%m", "date": "$timestamp"}},
                    "parameter": "$metadata.parameter",
                },
                "count": {"$sum": "$count"},
                "min": {"$min": "$min"},
                "max": {"$max": "$max"},
                "avg": {"$avg": "$avg"},
                "unit": {"$first": "$unit"},
            }},
            {"$sort": {"_id.month": 1, "_id.parameter": 1}},
        ]
        
        if report.parameters:
            pipeline[0]["$match"]["metadata.parameter"] = {"$in": report.parameters}
        
        data = []
        async for doc in db[Collections.MEASUREMENTS_1MIN].aggregate(pipeline):
            data.append({
                "month": doc["_id"]["month"],
                "parameter": doc["_id"]["parameter"],
                "count": doc["count"],
                "min": doc["min"],
                "max": doc["max"],
                "avg": round(doc["avg"], 2),
                "unit": doc["unit"],
            })
        
        return data
    
    async def _generate_custom_report(self, report: ReportInDB) -> List[Dict]:
        """Generate custom raw measurement report."""
        db = get_database()
        
        query = {
            "metadata.zone_id": report.zone_id,
            "timestamp": {"$gte": report.start, "$lte": report.end},
        }
        if report.parameters:
            query["metadata.parameter"] = {"$in": report.parameters}
        
        cursor = db[Collections.MEASUREMENTS].find(query).sort("timestamp", 1).limit(settings.REPORT_MAX_ROWS)
        
        data = []
        async for doc in cursor:
            data.append({
                "timestamp": doc["timestamp"].isoformat(),
                "zone_id": doc["metadata"]["zone_id"],
                "parameter": doc["metadata"]["parameter"],
                "value": doc["value"],
                "unit": doc["unit"],
                "device_id": doc["metadata"].get("device_id"),
            })
        
        return data
    
    async def _generate_alert_summary_report(self, report: ReportInDB) -> List[Dict]:
        """Generate alert summary report."""
        db = get_database()
        
        query = {
            "created_at": {"$gte": report.start, "$lte": report.end},
        }
        if report.zone_id:
            query["zone_id"] = report.zone_id
        
        cursor = db[Collections.ALERTS].find(query).sort("created_at", -1)
        
        data = []
        async for doc in cursor:
            data.append({
                "alert_id": str(doc["_id"]),
                "timestamp": doc["created_at"].isoformat(),
                "zone_id": doc["zone_id"],
                "parameter": doc["parameter"],
                "level": doc["level"],
                "status": doc["status"],
                "value": doc["value"],
                "threshold": doc["threshold"],
                "unit": doc["unit"],
                "message": doc["message"],
                "acknowledged_by": doc.get("acknowledged_by"),
                "acknowledged_at": doc.get("acknowledged_at").isoformat() if doc.get("acknowledged_at") else None,
                "resolved_by": doc.get("resolved_by"),
                "resolved_at": doc.get("resolved_at").isoformat() if doc.get("resolved_at") else None,
            })
        
        return data
    
    async def _generate_ai_weekly_report(self, report: ReportInDB) -> Dict:
        """Generate AI weekly report."""
        from app.services.ai_client import get_ai_client
        
        ai_client = get_ai_client()
        ai_report = await ai_client.weekly_report()
        
        if ai_report:
            return ai_report.model_dump(mode="json")
        return {"error": "AI service unavailable", "week_start": report.start.isoformat(), "week_end": report.end.isoformat()}
    
    # ============================================
    # File Writers
    # ============================================
    
    async def _save_csv(self, data: List[Dict], filepath: Path) -> None:
        """Save data as CSV."""
        if not data:
            # Write empty CSV with headers
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["No data available"])
            return
        
        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False)
    
    async def _save_json(self, data: Any, filepath: Path) -> None:
        """Save data as JSON."""
        import json
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    async def _save_pdf(self, data: Any, report: ReportInDB, filepath: Path) -> None:
        """Save data as PDF using ReportLab."""
        doc = SimpleDocTemplate(
            str(filepath),
            pagesize=landscape(A4),
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch,
        )
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=14,
            spaceAfter=12,
            alignment=1,  # Center
        )
        
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Heading2'],
            fontSize=11,
            spaceAfter=8,
        )
        
        normal_style = styles['Normal']
        normal_style.fontSize = 8
        
        elements = []
        
        # Title
        elements.append(Paragraph(f"Environmental Monitoring Report", title_style))
        elements.append(Paragraph(f"{report.title}", subtitle_style))
        elements.append(Spacer(1, 12))
        
        # Metadata table
        meta_data = [
            ["Report Type:", report.report_type.value],
            ["Format:", report.format.value],
            ["Period:", f"{report.start.strftime('%Y-%m-%d %H:%M')} to {report.end.strftime('%Y-%m-%d %H:%M')}"],
            ["Generated:", report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')],
            ["Generated By:", report.generated_by],
            ["Zone:", report.zone_id or "All Zones"],
        ]
        
        if report.parameters:
            meta_data.append(["Parameters:", ", ".join(report.parameters)])
        
        meta_table = Table(meta_data, colWidths=[1.5*inch, 6*inch])
        meta_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        
        elements.append(meta_table)
        elements.append(Spacer(1, 16))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        elements.append(Spacer(1, 12))
        
        # Data table
        if isinstance(data, list) and data:
            # Determine columns
            if report.report_type == ReportType.ALERT_SUMMARY:
                columns = ["Timestamp", "Zone", "Parameter", "Level", "Status", "Value", "Threshold", "Unit", "Message"]
                rows = [columns]
                for item in data[:500]:  # Limit rows for PDF
                    rows.append([
                        item.get("timestamp", "")[:19],
                        item.get("zone_id", ""),
                        item.get("parameter", ""),
                        item.get("level", ""),
                        item.get("status", ""),
                        f"{item.get('value', 0):.1f}",
                        f"{item.get('threshold', 0):.1f}",
                        item.get("unit", ""),
                        item.get("message", "")[:50],
                    ])
            else:
                # Measurement report
                columns = ["Timestamp", "Zone", "Parameter", "Count", "Min", "Max", "Avg", "Std", "Unit"]
                rows = [columns]
                for item in data[:500]:
                    rows.append([
                        item.get("timestamp", "")[:19] if "timestamp" in item else item.get("date", "") if "date" in item else item.get("week", "") if "week" in item else item.get("month", ""),
                        item.get("zone_id", "") if "zone_id" in item else report.zone_id or "",
                        item.get("parameter", ""),
                        str(item.get("count", "")),
                        f"{item.get('min', 0):.2f}" if item.get('min') is not None else "",
                        f"{item.get('max', 0):.2f}" if item.get('max') is not None else "",
                        f"{item.get('avg', 0):.2f}" if item.get('avg') is not None else "",
                        f"{item.get('std', 0):.2f}" if item.get('std') is not None else "",
                        item.get("unit", ""),
                    ])
            
            # Create table
            col_widths = [1.2*inch, 0.8*inch, 0.8*inch, 0.5*inch, 0.6*inch, 0.6*inch, 0.7*inch, 0.5*inch, 0.5*inch]
            if len(rows[0]) != len(col_widths):
                col_widths = [7.5*inch / len(rows[0])] * len(rows[0])
            
            table = Table(rows, colWidths=col_widths, repeatRows=1)
            table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F2F2')]),
            ]))
            
            elements.append(table)
            
            if len(data) > 500:
                elements.append(Spacer(1, 12))
                elements.append(Paragraph(f"Note: Showing first 500 of {len(data)} rows.", normal_style))
        
        elif isinstance(data, dict) and "error" not in data:
            # AI weekly report
            elements.append(Paragraph("AI Weekly Report", subtitle_style))
            elements.append(Spacer(1, 8))
            
            for zone_id, zone_data in data.get("zones", {}).items():
                elements.append(Paragraph(f"Zone: {zone_id}", styles['Heading3']))
                for key, value in zone_data.items():
                    elements.append(Paragraph(f"{key}: {value}", normal_style))
                elements.append(Spacer(1, 6))
        
        else:
            elements.append(Paragraph("No data available for the selected period.", normal_style))
        
        # Build PDF
        def add_page_number(canvas, doc):
            canvas.saveState()
            canvas.setFont('Helvetica', 8)
            page_num = canvas.getPageNumber()
            text = f"Page {page_num} | Environmental Monitoring Platform | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
            canvas.drawCentredString(A4[1]/2, 0.3*inch, text)
            canvas.restoreState()
        
        doc.build(elements, onFirstPage=add_page_number, onLaterPages=add_page_number)
    
    # ============================================
    # Report Management
    # ============================================
    
    async def get_report(self, report_id: str) -> Optional[ReportPublic]:
        """Get report by ID."""
        db = get_database()
        from bson import ObjectId
        
        doc = await db[Collections.REPORTS].find_one({"_id": ObjectId(report_id)})
        if doc:
            return ReportPublic.from_db(ReportInDB(**doc))
        return None
    
    async def list_reports(self, query_params) -> List[ReportPublic]:
        """List reports with filters."""
        db = get_database()
        
        filter_dict = {}
        if query_params.zone_id:
            filter_dict["zone_id"] = query_params.zone_id
        if query_params.report_type:
            filter_dict["report_type"] = query_params.report_type
        if query_params.generated_by:
            filter_dict["generated_by"] = query_params.generated_by
        if query_params.status:
            filter_dict["status"] = query_params.status
        if query_params.start or query_params.end:
            filter_dict["generated_at"] = {}
            if query_params.start:
                filter_dict["generated_at"]["$gte"] = query_params.start
            if query_params.end:
                filter_dict["generated_at"]["$lte"] = query_params.end
        
        cursor = db[Collections.REPORTS].find(filter_dict).sort("generated_at", -1).skip(query_params.offset).limit(query_params.limit)
        
        reports = []
        async for doc in cursor:
            reports.append(ReportPublic.from_db(ReportInDB(**doc)))
        return reports
    
    async def delete_report(self, report_id: str) -> bool:
        """Delete report and its file."""
        db = get_database()
        from bson import ObjectId
        
        report = await self.get_report(report_id)
        if not report:
            return False
        
        # Delete file
        if report.file_path:
            try:
                Path(report.file_path).unlink(missing_ok=True)
            except Exception as e:
                logger.warning("report_file_delete_failed", report_id=report_id, error=str(e))
        
        # Delete record
        result = await db[Collections.REPORTS].delete_one({"_id": ObjectId(report_id)})
        return result.deleted_count > 0
    
    async def get_download_path(self, report_id: str) -> Optional[Path]:
        """Get file path for download."""
        report = await self.get_report(report_id)
        if report and report.file_path and report.status == "completed":
            path = Path(report.file_path)
            if path.exists():
                return path
        return None


_report_service: Optional[ReportService] = None


def get_report_service() -> ReportService:
    """Get singleton ReportService instance."""
    global _report_service
    if _report_service is None:
        _report_service = ReportService()
    return _report_service