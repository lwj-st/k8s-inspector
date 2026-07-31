import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import {
  acknowledgeIssue,
  ApiClientError,
  getIssue,
  ignoreIssue,
  listIssueEvents,
  unignoreIssue,
} from "../api/client";
import type { Issue, IssueEvent } from "../api/types";
import { IssueDetailPanel } from "../components/IssueDetailPanel";

function readableError(reason: unknown) {
  if (reason instanceof ApiClientError) {
    return `${reason.message}${reason.requestId ? `（请求 ID：${reason.requestId}）` : ""}`;
  }
  return reason instanceof Error ? reason.message : "未知错误";
}

export function IssueDetailPage() {
  const params = useParams();
  const location = useLocation();
  const issueId = Number(params.id);
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const [issue, setIssue] = useState<Issue | null>(null);
  const [events, setEvents] = useState<IssueEvent[]>([]);
  const [eventsTotal, setEventsTotal] = useState(0);
  const [eventsPage, setEventsPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [eventsError, setEventsError] = useState<string | null>(null);

  const loadFirstPage = useCallback(async () => {
    if (!Number.isInteger(issueId) || issueId <= 0) {
      setError("问题编号无效");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    const issuePromise = getIssue(issueId);
    const eventsPromise = listIssueEvents(issueId, 1, 20);
    const [issueResult, eventsResult] = await Promise.allSettled([issuePromise, eventsPromise]);
    if (issueResult.status === "fulfilled") {
      setIssue(issueResult.value);
    } else {
      setError(readableError(issueResult.reason));
    }
    if (eventsResult.status === "fulfilled") {
      setEvents(eventsResult.value.items);
      setEventsTotal(eventsResult.value.total);
      setEventsPage(1);
      setEventsError(null);
    } else {
      setEventsError(readableError(eventsResult.reason));
    }
    setLoading(false);
  }, [issueId]);

  useEffect(() => {
    void loadFirstPage();
  }, [loadFirstPage]);

  async function loadMoreEvents() {
    const nextPage = eventsPage + 1;
    setEventsLoading(true);
    setEventsError(null);
    try {
      const result = await listIssueEvents(issueId, nextPage, 20);
      setEvents((current) => [...current, ...result.items]);
      setEventsTotal(result.total);
      setEventsPage(nextPage);
    } catch (reason) {
      setEventsError(readableError(reason));
    } finally {
      setEventsLoading(false);
    }
  }

  async function handleAcknowledge(note: string) {
    const updated = await acknowledgeIssue(issueId, note);
    setIssue(updated);
    await refreshEvents();
  }

  async function refreshEvents() {
    try {
      const refreshed = await listIssueEvents(issueId, 1, 20);
      setEvents(refreshed.items);
      setEventsTotal(refreshed.total);
      setEventsPage(1);
    } catch (reason) {
      setEventsError(readableError(reason));
    }
  }

  async function handleIgnore() {
    const updated = await ignoreIssue(issueId);
    setIssue(updated);
    await refreshEvents();
  }

  async function handleUnignore() {
    const updated = await unignoreIssue(issueId);
    setIssue(updated);
    await refreshEvents();
  }

  if (loading) {
    return <section className="page-section" aria-live="polite">正在读取问题详情…</section>;
  }

  if (error || !issue) {
    return (
      <section className="page-section">
        <div className="feedback-banner feedback-error" role="alert">
          问题详情读取失败：{error ?? "问题不存在或已清理"}
        </div>
        <div className="button-row">
          <button type="button" onClick={() => void loadFirstPage()}>重试</button>
          <Link className="text-link" to="/">返回问题工作台</Link>
        </div>
      </section>
    );
  }

  return (
    <section className="page-section issue-detail-page">
      <Link className="back-link" to={from}>← 返回问题列表</Link>
      <IssueDetailPanel
        issue={issue}
        events={events}
        eventsTotal={eventsTotal}
        eventsLoading={eventsLoading}
        eventsError={eventsError}
        onLoadMore={() => void loadMoreEvents()}
        onAcknowledge={handleAcknowledge}
        onIgnore={handleIgnore}
        onUnignore={handleUnignore}
      />
    </section>
  );
}
