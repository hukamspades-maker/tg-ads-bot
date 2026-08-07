"""
Database table definitions — async SQLAlchemy ORM models.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, Integer, String, Text, Index, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from dashboard.models.base import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")  # active, banned, floodwait, dead, idle
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_active: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    joined_groups: Mapped[int] = mapped_column(Integer, default=0)
    messages_sent: Mapped[int] = mapped_column(Integer, default=0)
    messages_failed: Mapped[int] = mapped_column(Integer, default=0)
    flood_count: Mapped[int] = mapped_column(Integer, default=0)
    spam_restricted: Mapped[bool] = mapped_column(Boolean, default=False)
    proxy_used: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    device_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    session_age_days: Mapped[int] = mapped_column(Integer, default=0)
    log_group_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_accounts_status", "status"),
        Index("ix_accounts_user_status", "user_id", "status"),
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    session_file: Mapped[str] = mapped_column(String(256), nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    login_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MessageStat(Base):
    __tablename__ = "message_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    account_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    group_id: Mapped[int] = mapped_column(Integer, nullable=False)
    group_title: Mapped[str] = mapped_column(String(256), default="")
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    send_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_msgstat_ts_success", "timestamp", "success"),
        Index("ix_msgstat_phone", "account_phone"),
    )


class LoginLog(Base):
    __tablename__ = "login_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    event: Mapped[str] = mapped_column(String(32), nullable=False)  # login, logout, failed, otp
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class TaskLog(Base):
    __tablename__ = "task_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)  # send, schedule, import, export
    status: Mapped[str] = mapped_column(String(32), default="running")  # running, completed, failed
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class FloodWait(Base):
    __tablename__ = "floodwaits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    wait_seconds: Mapped[int] = mapped_column(Integer, default=0)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class SchedulerTask(Base):
    __tablename__ = "scheduler_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    schedule_type: Mapped[str] = mapped_column(String(32), nullable=False)  # cron, interval
    schedule_config: Mapped[str] = mapped_column(Text, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AccountActivity(Base):
    __tablename__ = "account_activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    activity_type: Mapped[str] = mapped_column(String(32), nullable=False)  # join, leave, send, receive, flood
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class PerformanceStat(Base):
    __tablename__ = "performance_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_perfstat_name_ts", "metric_name", "timestamp"),
    )


class DashboardMetric(Base):
    __tablename__ = "dashboard_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)  # global, hourly, daily
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Float, default=0.0)
    period: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # today, yesterday, weekly, monthly
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_dashmetric_cat_key", "category", "key"),
    )
