"""Таблицы базы данных."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum

from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Role(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    EMPLOYEE = "employee"


class CheckoutMode(StrEnum):
    OFFICE = "office"
    FIELD = "field"


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default=Role.EMPLOYEE)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    attendances: Mapped[list[Attendance]] = relationship(back_populates="employee")

    @property
    def is_owner(self) -> bool:
        return self.role == Role.OWNER

    @property
    def is_manager(self) -> bool:
        return self.role in (Role.OWNER, Role.MANAGER)


class Attendance(Base):
    """Один рабочий день сотрудника: приход и уход."""

    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("employee_id", "work_date", name="uq_attendance_employee_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    is_workday: Mapped[bool] = mapped_column(default=True)

    check_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    check_in_lat: Mapped[float] = mapped_column(Float)
    check_in_lon: Mapped[float] = mapped_column(Float)
    check_in_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_in_distance_m: Mapped[float] = mapped_column(Float)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)

    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_out_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_out_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_out_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_out_mode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    early_leave_minutes: Mapped[int] = mapped_column(Integer, default=0)
    worked_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    employee: Mapped[Employee] = relationship(back_populates="attendances")


class Setting(Base):
    """Настройки, которые меняются во время работы (например, ID общего чата)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(500))
