"use client";

import { Fragment } from "react";
import { useTranslations } from "next-intl";
import {
  CalendarDays,
  Clock,
  GraduationCap,
  Mic,
  Pin,
  User,
} from "lucide-react";
import type { StructuredRecord } from "@/types/api";

/**
 * Render the LLM-extracted records as a grid of human-friendly cards.
 *
 * The internal `key: value;` rendering is great for embedding (every
 * field follows a predictable pattern) but unreadable for admins
 * verifying upload quality. This component re-projects the same data
 * with sensible visual hierarchy:
 *
 *   - the most identifying field (subject / dyscipline) as the title
 *   - group + level as a subtitle
 *   - day / date / time / room as a single horizontal meta row
 *   - teacher / lecturer at the bottom
 *
 * Anything we don't recognise still appears, just at the end of the
 * card under "additional details".
 */
export function RecordCards({ records }: { records: StructuredRecord[] }) {
  const t = useTranslations("admin.documents");
  if (!records.length) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        {t("noRecords")}
      </p>
    );
  }

  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {records.map((record, idx) => (
        <RecordCard key={idx} record={record} />
      ))}
    </div>
  );
}

/**
 * Reformat a time string into a normalised, human-readable form.
 *
 * The LLM occasionally collapses Ukrainian timetable cells like
 * "8:40–9:25 9:30–10:15" into "0840-0925 0930-1015" (no colons,
 * lonesome dash, multiple ranges glued together). This helper splits
 * the input on whitespace into individual ranges, inserts colons
 * after the hour, normalises any dash variant to a regular hyphen-
 * minus, and joins ranges with a comma so they read naturally.
 */
function formatTime(value: string): string {
  if (!value) return value;
  // Split into individual time tokens — anything separated by space
  // or by commas. We keep slashes ("/") as separators too because the
  // LLM sometimes uses them.
  const tokens = value.split(/[\s,/]+/).filter(Boolean);

  const formatted = tokens.map((token) => {
    // Replace any dash-like character with a plain hyphen, then split.
    const dashed = token.replace(/[‐-―−]/g, "-");
    const [start, end] = dashed.split("-");
    return [start, end]
      .filter((part) => part)
      .map(insertColon)
      .join("–");
  });

  return formatted.join(", ");
}

function insertColon(part: string): string {
  const trimmed = part.trim();
  if (!trimmed) return trimmed;
  if (trimmed.includes(":")) return trimmed; // already formatted
  // 4-digit form (e.g. "0840") — split into HH:MM.
  if (/^\d{4}$/.test(trimmed)) {
    return `${trimmed.slice(0, 2)}:${trimmed.slice(2)}`;
  }
  // 3-digit form ("840" → "8:40").
  if (/^\d{3}$/.test(trimmed)) {
    return `${trimmed.slice(0, 1)}:${trimmed.slice(1)}`;
  }
  return trimmed;
}

const KNOWN_KEYS = new Set([
  "type",
  "level",
  "course",
  "group",
  "subject",
  "lesson_kind",
  "day",
  "date",
  "exam_date",
  "consultation_date",
  "time",
  "exam_time",
  "consultation_time",
  "room",
  "exam_room",
  "consultation_room",
  "teacher",
]);

function RecordCard({ record }: { record: StructuredRecord }) {
  const t = useTranslations("admin.documents");

  const subject = (record.subject as string | null) ?? null;
  const lessonKind = (record.lesson_kind as string | null) ?? null;
  const group = (record.group as string | null) ?? null;
  const level = (record.level as string | null) ?? null;
  const teacher = (record.teacher as string | null) ?? null;

  // Collect day/date/time/room into one ordered list of meta entries
  // so each card displays whatever the source actually provides
  // without shoehorning class records into an exam shape and vice
  // versa.
  const meta: { icon: React.ReactNode; value: string }[] = [];
  if (record.day) {
    meta.push({ icon: <CalendarDays className="h-3 w-3" />, value: String(record.day) });
  }
  if (record.date) {
    meta.push({ icon: <CalendarDays className="h-3 w-3" />, value: String(record.date) });
  }
  if (record.consultation_date) {
    const time = record.consultation_time
      ? formatTime(String(record.consultation_time))
      : "";
    meta.push({
      icon: <CalendarDays className="h-3 w-3" />,
      value: `${t("consultationShort")}: ${record.consultation_date}${
        time ? ` ${time}` : ""
      }`,
    });
  }
  if (record.exam_date) {
    const time = record.exam_time
      ? formatTime(String(record.exam_time))
      : "";
    meta.push({
      icon: <CalendarDays className="h-3 w-3" />,
      value: `${t("examShort")}: ${record.exam_date}${
        time ? ` ${time}` : ""
      }`,
    });
  }
  if (record.time && !record.consultation_date && !record.exam_date) {
    meta.push({
      icon: <Clock className="h-3 w-3" />,
      value: formatTime(String(record.time)),
    });
  }
  if (record.room) {
    meta.push({ icon: <Pin className="h-3 w-3" />, value: String(record.room) });
  }
  if (record.exam_room && record.exam_room !== record.room) {
    meta.push({
      icon: <Pin className="h-3 w-3" />,
      value: `${t("examShort")}: ${record.exam_room}`,
    });
  }

  const extras = Object.entries(record).filter(
    ([key, value]) => !KNOWN_KEYS.has(key) && value != null && value !== "",
  );

  return (
    <div className="rounded-md border bg-background px-3 py-2.5 text-xs">
      <div className="mb-1 flex items-center gap-2">
        {record.type && <TypeBadge type={String(record.type)} />}
        <span className="text-muted-foreground">
          {[level, group].filter(Boolean).join(" · ") || t("groupAny")}
        </span>
      </div>

      {subject ? (
        <p className="font-medium text-foreground leading-snug">
          {subject}
          {lessonKind && (
            <span className="ml-1 font-normal text-muted-foreground">
              ({lessonKind})
            </span>
          )}
        </p>
      ) : (
        lessonKind && (
          <p className="text-muted-foreground">{lessonKind}</p>
        )
      )}

      {meta.length > 0 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground">
          {meta.map((m, i) => (
            <span key={i} className="inline-flex items-center gap-1">
              {m.icon}
              {m.value}
            </span>
          ))}
        </div>
      )}

      {teacher && (
        <p className="mt-1.5 inline-flex items-center gap-1 text-muted-foreground">
          <User className="h-3 w-3" />
          {teacher}
        </p>
      )}

      {extras.length > 0 && (
        <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-2 gap-y-0.5 border-t pt-1.5 text-[10px] text-muted-foreground/70">
          {/* React.Fragment must carry the key — a shorthand <></>
            * fragment cannot accept props, so the warning fires even
            * though we set keys on the children. */}
          {extras.map(([key, value]) => (
            <Fragment key={key}>
              <dt className="font-medium">{key}</dt>
              <dd>{String(value)}</dd>
            </Fragment>
          ))}
        </dl>
      )}
    </div>
  );
}

function TypeBadge({ type }: { type: string }) {
  const t = useTranslations("admin.documents.recordType");
  // We don't lowercase user-provided values blindly — only known types
  // map to a translated label, anything else passes through as-is.
  const normalised = type.toLowerCase();
  const known = new Set(["class", "exam", "credit", "test", "consultation"]);
  const label = known.has(normalised) ? t(normalised) : type;

  const palette: Record<string, string> = {
    class: "bg-blue-500/10 text-blue-700 dark:text-blue-300",
    exam: "bg-red-500/10 text-red-700 dark:text-red-300",
    credit: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    test: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    consultation: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
  };
  const colour = palette[normalised] ?? "bg-muted text-muted-foreground";

  const Icon = normalised === "class" ? Mic : GraduationCap;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${colour}`}
    >
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}
