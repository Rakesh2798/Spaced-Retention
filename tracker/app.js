/* ============================================================
   Spaced Retention — Application Logic
   ============================================================
   Each topic stores its own explicit reviewDates array.
   For new topics, each review date is the prior checkpoint plus a fixed gap:
   +2, +4, +8, +15, +22, +28, +31, +61 days (R1 from studied date).
   Data persisted in localStorage.
   ============================================================ */

(() => {
    'use strict';

    // ──── Constants ────
    const STORAGE_KEY = 'spacedRetention_topics';
    const STREAK_KEY = 'spacedRetention_streak';
    const SEEDED_KEY = 'spacedRetention_seeded_v2';
    const TOPIC_TABS_KEY = 'spacedRetention_topic_tabs';
    const THEME_KEY = 'spacedRetention_theme';
    const API_KEY_KEY = 'spacedRetention_api_key';
    const API_BASE_URL = 'http://localhost:5000/api'; // Change this when deployed

    // Days added after each checkpoint (studied date for R1, prior review for R2+)
    const REVIEW_GAPS = [2, 4, 8, 15, 22, 28, 31, 61];
    // Legacy flat offsets from studied date (incorrect — used only for migration)
    const OLD_REVIEW_INTERVALS = [1, 3, 7, 14, 21, 28, 30, 60];
    const REVIEW_LABELS = ['+1 Day', '+3 Days', '+7 Days', '+14 Days', '+21 Days', '+28 Days', '+30 Days', '+60 Days'];

    // ──── State ────
    let topics = [];
    let topicTabs = ['Python', 'OOPs'];
    let activeTopicTab = 'all';
    let resetTargetId = null;
    let deleteTargetId = null;

    // ──── Seed Data (from user's spreadsheet) ────
    const SEED_DATA = [
        { name: "What is Python?", studiedDate: "2026-06-23", reviewDates: ["2026-06-25","2026-06-29","2026-07-07","2026-07-22","2026-08-13","2026-09-12","2026-10-13","2026-12-13"] },
        { name: "What is Language?", studiedDate: "2026-06-23", reviewDates: ["2026-06-25","2026-06-29","2026-07-07","2026-07-22","2026-08-13","2026-09-12","2026-10-13","2026-12-13"] },
        { name: "Types of Language", studiedDate: "2026-06-23", reviewDates: ["2026-06-25","2026-06-29","2026-07-07","2026-07-22","2026-08-13","2026-09-12","2026-10-13","2026-12-13"] },
        { name: "Dynamically Typed", studiedDate: "2026-06-23", reviewDates: ["2026-06-25","2026-06-29","2026-07-07","2026-07-22","2026-08-13","2026-09-12","2026-10-13","2026-12-13"] },
        { name: "What is Operating System?", studiedDate: "2026-06-23", reviewDates: ["2026-06-25","2026-06-29","2026-07-07","2026-07-22","2026-08-13","2026-09-12","2026-10-13","2026-12-13"] },
        { name: "What are Variables?", studiedDate: "2026-06-23", reviewDates: ["2026-06-25","2026-06-29","2026-07-07","2026-07-22","2026-08-13","2026-09-12","2026-10-13","2026-12-13"] },
        { name: "What are Identifiers?", studiedDate: "2026-06-23", reviewDates: ["2026-06-25","2026-06-29","2026-07-07","2026-07-22","2026-08-13","2026-09-12","2026-10-13","2026-12-13"] },
        { name: "Rules of Identifiers?", studiedDate: "2026-06-23", reviewDates: ["2026-06-25","2026-06-29","2026-07-07","2026-07-22","2026-08-13","2026-09-12","2026-10-13","2026-12-13"] },
        { name: "What are Keywords?", studiedDate: "2026-06-23", reviewDates: ["2026-06-25","2026-06-29","2026-07-07","2026-07-22","2026-08-13","2026-09-12","2026-10-13","2026-12-13"] },
        { name: "Based on Compiler and Interpreter?", studiedDate: "2026-06-23", reviewDates: ["2026-06-25","2026-06-29","2026-07-07","2026-07-22","2026-08-13","2026-09-12","2026-10-13","2026-12-13"] },
        { name: "What is Data?", studiedDate: "2026-06-23", reviewDates: ["2026-06-25","2026-06-29","2026-07-07","2026-07-22","2026-08-13","2026-09-12","2026-10-13","2026-12-13"] },
        { name: "What are Datatypes?", studiedDate: "2026-06-23", reviewDates: ["2026-06-25","2026-06-29","2026-07-07","2026-07-22","2026-08-13","2026-09-12","2026-10-13","2026-12-13"] },
        { name: "What is User Input in Python?", studiedDate: "2026-06-23", reviewDates: ["2026-06-25","2026-06-29","2026-07-07","2026-07-22","2026-08-13","2026-09-12","2026-10-13","2026-12-13"] },
        { name: "What is Typecasting or Pythoncasting?", studiedDate: "2026-06-23", reviewDates: ["2026-06-25","2026-06-29","2026-07-07","2026-07-22","2026-08-13","2026-09-12","2026-10-13","2026-12-13"] },
        { name: "Explain Operators?", studiedDate: "2026-06-23", reviewDates: ["2026-06-25","2026-06-29","2026-07-07","2026-07-22","2026-08-13","2026-09-12","2026-10-13","2026-12-13"] },
        { name: "Explain Comment line?", studiedDate: "2026-06-23", reviewDates: ["2026-06-25","2026-06-29","2026-07-07","2026-07-22","2026-08-13","2026-09-12","2026-10-13","2026-12-13"] },
        { name: "Explain Control Flow Statements?", studiedDate: "2026-06-27", reviewDates: ["2026-06-29","2026-07-03","2026-07-11","2026-07-26","2026-08-17","2026-09-14","2026-10-15","2026-12-15"] },
    ];

    // ──── Utilities ────
    function generateId() {
        return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    }

    function toDateStr(date) {
        const d = new Date(date);
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
    }

    function formatDateShort(dateStr) {
        const d = new Date(dateStr + 'T00:00:00');
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
    }

    function addDays(dateStr, days) {
        const d = new Date(dateStr + 'T00:00:00');
        d.setDate(d.getDate() + days);
        return toDateStr(d);
    }

    function todayStr() {
        return toDateStr(new Date());
    }

    function daysDiff(dateStr1, dateStr2) {
        const d1 = new Date(dateStr1 + 'T00:00:00');
        const d2 = new Date(dateStr2 + 'T00:00:00');
        return Math.round((d2 - d1) / (1000 * 60 * 60 * 24));
    }

    function computeReviewDates(studiedDate) {
        const dates = [];
        let anchor = studiedDate;
        for (const gap of REVIEW_GAPS) {
            anchor = addDays(anchor, gap);
            dates.push(anchor);
        }
        return dates;
    }

    function matchesOldReviewSchedule(topic) {
        return topic.reviewDates.every((date, idx) => {
            return date === addDays(topic.studiedDate, OLD_REVIEW_INTERVALS[idx]);
        });
    }

    function normalizeTopicTab(name) {
        return name.trim().replace(/\s+/g, ' ');
    }

    function inferTopicTab(topicName) {
        const lowerName = topicName.toLowerCase();
        if (lowerName.includes('oop')) return 'OOPs';
        return 'Python';
    }

    function ensureTopicTab(name) {
        const tabName = normalizeTopicTab(name);
        if (!tabName) return;
        if (!topicTabs.some(tab => tab.toLowerCase() === tabName.toLowerCase())) {
            topicTabs.push(tabName);
        }
    }

    function topicBelongsToActiveTab(topic) {
        return activeTopicTab === 'all' || topic.topicTab === activeTopicTab;
    }

    function filteredTopicsByTab() {
        return topics.filter(topicBelongsToActiveTab);
    }

    // ──── Theme ────
    function getTheme() {
        return document.documentElement.getAttribute('data-theme') || 'dark';
    }

    function updateThemeToggleUI(theme) {
        const btn = document.getElementById('btn-theme-toggle');
        if (!btn) return;

        const isDark = theme === 'dark';
        const label = isDark ? 'Switch to light mode' : 'Switch to dark mode';
        btn.title = label;
        btn.setAttribute('aria-label', label);
    }

    function setTheme(theme) {
        const nextTheme = theme === 'light' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', nextTheme);
        localStorage.setItem(THEME_KEY, nextTheme);
        updateThemeToggleUI(nextTheme);
    }

    function toggleTheme() {
        setTheme(getTheme() === 'dark' ? 'light' : 'dark');
    }

    function initTheme() {
        const saved = localStorage.getItem(THEME_KEY);
        const theme = saved || (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
        setTheme(theme);
    }

    // ──── API Integration ────
    async function apiRequest(endpoint, method = 'GET', data = null) {
        const apiKey = localStorage.getItem(API_KEY_KEY);
        const headers = {
            'Content-Type': 'application/json'
        };
        if (apiKey) {
            headers['X-API-Key'] = apiKey;
        }

        const options = {
            method,
            headers
        };

        if (data) {
            options.body = JSON.stringify(data);
        }

        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.error || 'API request failed');
            }
            return result;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    }

    async function saveToCloud() {
        const apiKey = localStorage.getItem(API_KEY_KEY);
        if (!apiKey) return false;

        try {
            const data = {
                [STORAGE_KEY]: topics,
                [TOPIC_TABS_KEY]: topicTabs,
                [STREAK_KEY]: loadStreak(),
                [THEME_KEY]: getTheme()
            };
            await apiRequest('/data', 'POST', data);
            return true;
        } catch (error) {
            console.error('Failed to save to cloud:', error);
            return false;
        }
    }

    async function loadFromCloud() {
        const apiKey = localStorage.getItem(API_KEY_KEY);
        if (!apiKey) return false;

        try {
            const data = await apiRequest('/data', 'GET');
            if (data[STORAGE_KEY]) {
                topics = data[STORAGE_KEY].value;
                topicTabs = data[TOPIC_TABS_KEY]?.value || ['Python', 'OOPs'];
                if (data[STREAK_KEY]) {
                    localStorage.setItem(STREAK_KEY, JSON.stringify(data[STREAK_KEY].value));
                }
                if (data[THEME_KEY]) {
                    setTheme(data[THEME_KEY].value);
                }
                return true;
            }
            return false;
        } catch (error) {
            console.error('Failed to load from cloud:', error);
            return false;
        }
    }

    // ──── Persistence ────
    function save() {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(topics));
        localStorage.setItem(TOPIC_TABS_KEY, JSON.stringify(topicTabs));
        saveToCloud(); // Try to save to cloud in background
    }

    function load() {
        const apiKey = localStorage.getItem(API_KEY_KEY);
        
        // Try to load from cloud first if authenticated
        if (apiKey) {
            loadFromCloud().then(success => {
                if (success) {
                    render();
                } else {
                    loadFromLocal();
                }
            });
        } else {
            loadFromLocal();
        }
    }

    function loadFromLocal() {
        try {
            const data = localStorage.getItem(STORAGE_KEY);
            topics = data ? JSON.parse(data) : [];
            const tabsData = localStorage.getItem(TOPIC_TABS_KEY);
            const savedTabs = tabsData ? JSON.parse(tabsData) : [];
            topicTabs = Array.isArray(savedTabs) && savedTabs.length ? savedTabs : ['Python', 'OOPs'];

            // Migration: ensure each topic has reviewDates and reviews
            topics.forEach(t => {
                if (!t.reviews) {
                    t.reviews = new Array(8).fill(false);
                }
                while (t.reviews.length < 8) t.reviews.push(false);

                if (!t.reviewDates) {
                    t.reviewDates = computeReviewDates(t.studiedDate);
                }
                while (t.reviewDates.length < 8) {
                    const lastDate = t.reviewDates[t.reviewDates.length - 1] || t.studiedDate;
                    t.reviewDates.push(addDays(lastDate, 30));
                }
                if (!t.reviews.some(Boolean) && matchesOldReviewSchedule(t)) {
                    t.reviewDates = computeReviewDates(t.studiedDate);
                }
                if (!t.topicTab) {
                    t.topicTab = inferTopicTab(t.name);
                }
                ensureTopicTab(t.topicTab);
            });
            ensureTopicTab('Python');
            ensureTopicTab('OOPs');
            save();
        } catch {
            topics = [];
            topicTabs = ['Python', 'OOPs'];
        }
    }

    function seedIfNeeded() {
        if (localStorage.getItem(SEEDED_KEY)) return;

        // Check if there are already topics with these names to avoid duplicates
        const existingNames = new Set(topics.map(t => t.name.toLowerCase()));

        SEED_DATA.forEach(seed => {
            if (existingNames.has(seed.name.toLowerCase())) return;

            topics.push({
                id: generateId(),
                name: seed.name,
                topicTab: inferTopicTab(seed.name),
                studiedDate: seed.studiedDate,
                reviewDates: [...seed.reviewDates],
                reviews: new Array(8).fill(false),
                createdAt: new Date().toISOString()
            });
        });

        save();
        localStorage.setItem(SEEDED_KEY, 'true');
    }

    // ──── Streak ────
    function loadStreak() {
        try {
            const data = localStorage.getItem(STREAK_KEY);
            return data ? JSON.parse(data) : { count: 0, lastDate: null };
        } catch {
            return { count: 0, lastDate: null };
        }
    }

    function updateStreak() {
        const streak = loadStreak();
        const today = todayStr();

        if (streak.lastDate === today) return streak.count;

        const yesterday = addDays(today, -1);
        if (streak.lastDate === yesterday) {
            streak.count += 1;
        } else {
            streak.count = 1;
        }
        streak.lastDate = today;
        localStorage.setItem(STREAK_KEY, JSON.stringify(streak));
        return streak.count;
    }

    function getStreak() {
        const streak = loadStreak();
        const today = todayStr();
        const yesterday = addDays(today, -1);

        if (streak.lastDate === today || streak.lastDate === yesterday) {
            return streak.count;
        }
        return 0;
    }

    // ──── Toast Notifications ────
    let toastContainer = null;

    function showToast(message, type = 'success') {
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'toast-container';
            document.body.appendChild(toastContainer);
        }

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('toast-exit');
            setTimeout(() => toast.remove(), 300);
        }, 2800);
    }

    // ──── Review Status Logic ────
    function getReviewStatus(topic, reviewIndex) {
        if (topic.reviews[reviewIndex]) return 'done';

        const reviewDate = topic.reviewDates[reviewIndex];
        const today = todayStr();
        const diff = daysDiff(today, reviewDate);

        if (diff < 0) return 'overdue';
        if (diff === 0) return 'due';
        return 'future';
    }

    function getDueReviews() {
        const today = todayStr();
        const dueItems = [];

        filteredTopicsByTab().forEach(topic => {
            topic.reviews.forEach((done, idx) => {
                if (done) return;
                const reviewDate = topic.reviewDates[idx];
                const diff = daysDiff(today, reviewDate);
                if (diff <= 0) {
                    dueItems.push({
                        topicId: topic.id,
                        topicName: topic.name,
                        reviewIndex: idx,
                        reviewDate: reviewDate,
                        isOverdue: diff < 0,
                        daysDiff: Math.abs(diff)
                    });
                }
            });
        });

        // Sort: overdue first (most overdue on top), then due today
        dueItems.sort((a, b) => {
            if (a.isOverdue && !b.isOverdue) return -1;
            if (!a.isOverdue && b.isOverdue) return 1;
            return b.daysDiff - a.daysDiff;
        });

        return dueItems;
    }

    // ──── Rendering ────
    function render() {
        renderTopicTabs();
        renderStats();
        renderDueSection();
        renderTable();
        updateCurrentDate();
    }

    function updateCurrentDate() {
        const now = new Date();
        const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
        document.getElementById('current-date').textContent = now.toLocaleDateString('en-US', options);
    }

    function renderStats() {
        const dueReviews = getDueReviews();
        const visibleTopics = filteredTopicsByTab();
        const completed = visibleTopics.filter(t => t.reviews.every(r => r)).length;
        const streak = getStreak();

        document.getElementById('due-count').textContent = dueReviews.length;
        document.getElementById('total-count').textContent = visibleTopics.length;
        document.getElementById('completed-count').textContent = completed;
        document.getElementById('streak-count').textContent = streak;
    }

    function renderTopicTabs() {
        const tabsEl = document.getElementById('topic-tabs');
        tabsEl.innerHTML = '';

        tabsEl.appendChild(buildTopicTabButton('All', 'all', topics.length));

        topicTabs.forEach(tabName => {
            const count = topics.filter(topic => topic.topicTab === tabName).length;
            tabsEl.appendChild(buildTopicTabButton(tabName, tabName, count));
        });
    }

    function buildTopicTabButton(label, value, count) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `topic-tab ${activeTopicTab === value ? 'active' : ''}`;
        button.setAttribute('role', 'tab');
        button.setAttribute('aria-selected', activeTopicTab === value ? 'true' : 'false');
        if (value !== 'all') {
            button.title = `${label} (Double-click to rename)`;
        } else {
            button.title = label;
        }
        button.innerHTML = `
            <span class="topic-tab-name">${escapeHtml(label)}</span>
            <span class="topic-tab-count">${count}</span>
            <span class="topic-tab-caret"></span>
        `;
        button.addEventListener('click', () => {
            activeTopicTab = value;
            render();
        });

        if (value !== 'all') {
            button.addEventListener('dblclick', (e) => {
                e.stopPropagation();
                const newName = prompt(`Rename tab "${label}" to:`, label);
                if (newName !== null) {
                    const trimmed = newName.trim();
                    if (trimmed && trimmed !== label) {
                        renameTopicTab(label, trimmed);
                    }
                }
            });
        }

        return button;
    }

    function renderDueSection() {
        const dueItems = getDueReviews();
        const section = document.getElementById('due-section');
        const list = document.getElementById('due-list');

        if (dueItems.length === 0) {
            section.style.display = 'none';
            return;
        }

        section.style.display = '';
        list.innerHTML = '';

        dueItems.forEach(item => {
            const div = document.createElement('div');
            div.className = `due-item ${item.isOverdue ? 'due-item-overdue' : ''}`;

            const overdueLabel = item.isOverdue
                ? `Overdue by ${item.daysDiff} day${item.daysDiff !== 1 ? 's' : ''}`
                : 'Due today';

            div.innerHTML = `
                <div class="due-item-info">
                    <span class="due-item-topic">${escapeHtml(item.topicName)}</span>
                    <span class="due-item-review">Review ${item.reviewIndex + 1} · ${formatDateShort(item.reviewDate)} · ${overdueLabel}</span>
                </div>
                <div class="due-item-actions">
                    <button class="btn-check" title="Mark as done" data-topic="${item.topicId}" data-review="${item.reviewIndex}">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                    </button>
                </div>
            `;

            const checkBtn = div.querySelector('.btn-check');
            checkBtn.addEventListener('click', () => {
                markReviewDone(item.topicId, item.reviewIndex);
            });

            list.appendChild(div);
        });
    }

    function renderTable() {
        const tbody = document.getElementById('topics-tbody');
        const emptyState = document.getElementById('empty-state');
        const searchTerm = document.getElementById('search-input').value.toLowerCase();
        const filterValue = document.getElementById('filter-select').value;

        let filtered = filteredTopicsByTab();

        // Search filter
        if (searchTerm) {
            filtered = filtered.filter(t => t.name.toLowerCase().includes(searchTerm));
        }

        // Category filter
        const today = todayStr();
        if (filterValue === 'due') {
            filtered = filtered.filter(t => {
                return t.reviews.some((done, idx) => {
                    if (done) return false;
                    return t.reviewDates[idx] === today;
                });
            });
        } else if (filterValue === 'overdue') {
            filtered = filtered.filter(t => {
                return t.reviews.some((done, idx) => {
                    if (done) return false;
                    return daysDiff(today, t.reviewDates[idx]) < 0;
                });
            });
        } else if (filterValue === 'completed') {
            filtered = filtered.filter(t => t.reviews.every(r => r));
        } else if (filterValue === 'in-progress') {
            filtered = filtered.filter(t => t.reviews.some(r => r) && !t.reviews.every(r => r));
        }

        if (filtered.length === 0 && topics.length === 0) {
            tbody.innerHTML = '';
            emptyState.style.display = '';
            return;
        }

        emptyState.style.display = 'none';

        if (filtered.length === 0) {
            tbody.innerHTML = `<tr><td colspan="12" style="text-align:center; padding:32px; color:var(--text-muted);">No topics match this tab or filter.</td></tr>`;
            return;
        }

        // Sort: newest studied first
        filtered.sort((a, b) => new Date(b.studiedDate) - new Date(a.studiedDate));

        tbody.innerHTML = '';

        filtered.forEach(topic => {
            const tr = document.createElement('tr');
            const completedCount = topic.reviews.filter(r => r).length;
            const progress = Math.round((completedCount / 8) * 100);
            const isComplete = completedCount === 8;

            let reviewCells = '';
            for (let i = 0; i < 8; i++) {
                const status = getReviewStatus(topic, i);
                const dateLabel = formatDateShort(topic.reviewDates[i]);

                let badge = '';
                if (status === 'done') {
                    badge = `<span class="review-badge review-done" title="Completed on ${dateLabel} — Click to undo" data-topic="${topic.id}" data-review="${i}"><span class="review-done-date">${dateLabel}</span><span class="review-done-status">Done</span></span>`;
                } else if (status === 'due') {
                    badge = `<span class="review-badge review-due" title="Due today — click to complete" data-topic="${topic.id}" data-review="${i}">${dateLabel}</span>`;
                } else if (status === 'overdue') {
                    const days = Math.abs(daysDiff(todayStr(), topic.reviewDates[i]));
                    badge = `<span class="review-badge review-overdue" title="Overdue by ${days} days — click to complete" data-topic="${topic.id}" data-review="${i}">${dateLabel}</span>`;
                } else {
                    badge = `<span class="review-badge review-future" title="${dateLabel}">${dateLabel}</span>`;
                }
                reviewCells += `<td class="review-cell">${badge}</td>`;
            }

            tr.innerHTML = `
                <td><span class="topic-name" title="Double click to edit" data-id="${topic.id}">${escapeHtml(topic.name)}</span></td>
                <td class="date-cell">${formatDateShort(topic.studiedDate)}</td>
                ${reviewCells}
                <td class="progress-cell">
                    <div class="progress-wrapper">
                        <div class="progress-bar">
                            <div class="progress-fill ${isComplete ? 'complete' : ''}" style="width:${progress}%"></div>
                        </div>
                        <span class="progress-text">${completedCount}/8</span>
                    </div>
                </td>
                <td class="actions-cell">
                    <div class="actions-group">
                        <button class="btn-icon reset" title="Reset topic" data-action="reset" data-id="${topic.id}">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 105.42-8.78L1 10"/></svg>
                        </button>
                        <button class="btn-icon danger" title="Delete topic" data-action="delete" data-id="${topic.id}">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
                        </button>
                    </div>
                </td>
            `;

            tbody.appendChild(tr);
        });

        // Attach inline editing handlers for topic name
        tbody.querySelectorAll('.topic-name').forEach(span => {
            span.addEventListener('dblclick', () => {
                const topicId = span.dataset.id;
                const topic = topics.find(t => t.id === topicId);
                if (!topic) return;

                const originalName = topic.name;
                span.contentEditable = 'true';
                span.classList.add('editing');
                span.focus();

                // Select all text
                const range = document.createRange();
                range.selectNodeContents(span);
                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);

                const finishEdit = (commit) => {
                    if (span.contentEditable !== 'true') return;
                    span.contentEditable = 'false';
                    span.classList.remove('editing');
                    
                    if (commit) {
                        const newName = span.textContent.trim();
                        if (newName && newName !== originalName) {
                            renameTopic(topicId, newName);
                        } else {
                            span.textContent = originalName;
                        }
                    } else {
                        span.textContent = originalName;
                    }
                };

                span.addEventListener('blur', () => finishEdit(true), { once: true });
                
                span.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        span.blur();
                    } else if (e.key === 'Escape') {
                        finishEdit(false);
                        span.blur();
                    }
                });
            });
        });

        // Attach click handlers for review badges (done/due/overdue)
        tbody.querySelectorAll('.review-done, .review-due, .review-overdue').forEach(badge => {
            badge.addEventListener('click', () => {
                const topicId = badge.dataset.topic;
                const reviewIndex = parseInt(badge.dataset.review);
                toggleReview(topicId, reviewIndex);
            });
        });

        // Attach click handlers for action buttons
        tbody.querySelectorAll('[data-action="reset"]').forEach(btn => {
            btn.addEventListener('click', () => openResetModal(btn.dataset.id));
        });

        tbody.querySelectorAll('[data-action="delete"]').forEach(btn => {
            btn.addEventListener('click', () => openDeleteModal(btn.dataset.id));
        });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ──── Actions ────
    function addTopic(name, studiedDate) {
        const topicTab = activeTopicTab === 'all' ? 'Python' : activeTopicTab;
        ensureTopicTab(topicTab);

        const topic = {
            id: generateId(),
            name: name.trim(),
            topicTab,
            studiedDate: studiedDate,
            reviewDates: computeReviewDates(studiedDate),
            reviews: new Array(8).fill(false),
            createdAt: new Date().toISOString()
        };
        topics.push(topic);
        save();
        render();
        showToast(`"${topic.name}" added`, 'success');
    }

    function renameTopicTab(oldName, newName) {
        const normalizedOld = normalizeTopicTab(oldName);
        const normalizedNew = normalizeTopicTab(newName);
        if (!normalizedNew) return;
        if (normalizedOld.toLowerCase() === normalizedNew.toLowerCase()) return;

        // Check if destination tab already exists
        const exists = topicTabs.some(tab => tab.toLowerCase() === normalizedNew.toLowerCase());
        if (exists) {
            showToast(`Tab "${normalizedNew}" already exists`, 'error');
            return;
        }

        // Rename in topicTabs
        const idx = topicTabs.findIndex(tab => tab.toLowerCase() === normalizedOld.toLowerCase());
        if (idx !== -1) {
            topicTabs[idx] = normalizedNew;
        }

        // Rename in topics
        topics.forEach(topic => {
            if (topic.topicTab && topic.topicTab.toLowerCase() === normalizedOld.toLowerCase()) {
                topic.topicTab = normalizedNew;
            }
        });

        // Update active tab if it was renamed
        if (activeTopicTab.toLowerCase() === normalizedOld.toLowerCase()) {
            activeTopicTab = normalizedNew;
        }

        save();
        render();
        showToast(`Renamed "${normalizedOld}" to "${normalizedNew}"`, 'success');
    }

    function renameTopic(topicId, newName) {
        const topic = topics.find(t => t.id === topicId);
        if (!topic) return;

        const oldName = topic.name;
        topic.name = newName.trim();
        save();
        render();
        showToast(`Topic renamed to "${topic.name}"`, 'success');
    }

    function toggleReview(topicId, reviewIndex) {
        const topic = topics.find(t => t.id === topicId);
        if (!topic) return;

        const isDone = topic.reviews[reviewIndex];
        topic.reviews[reviewIndex] = !isDone;
        save();
        if (topic.reviews[reviewIndex]) {
            updateStreak();
            showToast(`Review ${reviewIndex + 1} completed for "${topic.name}"`, 'success');
        } else {
            showToast(`Review ${reviewIndex + 1} marked incomplete for "${topic.name}"`, 'info');
        }
        render();
    }

    function markAllDueComplete() {
        const dueItems = getDueReviews();
        if (dueItems.length === 0) return;

        dueItems.forEach(item => {
            const topic = topics.find(t => t.id === item.topicId);
            if (topic) {
                topic.reviews[item.reviewIndex] = true;
            }
        });

        save();
        updateStreak();
        render();
        showToast(`${dueItems.length} review${dueItems.length !== 1 ? 's' : ''} marked complete`, 'success');
    }

    function resetTopic(topicId) {
        const topic = topics.find(t => t.id === topicId);
        if (!topic) return;

        topic.studiedDate = todayStr();
        topic.reviewDates = computeReviewDates(topic.studiedDate);
        topic.reviews = new Array(8).fill(false);
        save();
        render();
        showToast(`"${topic.name}" has been reset`, 'info');
    }

    function deleteTopic(topicId) {
        const topic = topics.find(t => t.id === topicId);
        if (!topic) return;

        const name = topic.name;
        topics = topics.filter(t => t.id !== topicId);
        save();
        render();
        showToast(`"${name}" deleted`, 'error');
    }

    // ──── Export / Import ────
    function exportData() {
        const data = {
            version: 2,
            exportedAt: new Date().toISOString(),
            topics: topics,
            streak: loadStreak()
        };

        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `spaced-retention-backup-${todayStr()}.json`;
        a.click();
        URL.revokeObjectURL(url);
        showToast('Data exported successfully', 'success');
    }

    function importData(file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const data = JSON.parse(e.target.result);
                if (data.topics && Array.isArray(data.topics)) {
                    const existingIds = new Set(topics.map(t => t.id));
                    let imported = 0;
                    data.topics.forEach(t => {
                        if (!existingIds.has(t.id)) {
                            if (!t.reviews) t.reviews = new Array(8).fill(false);
                            while (t.reviews.length < 8) t.reviews.push(false);
                            if (!t.reviewDates) t.reviewDates = computeReviewDates(t.studiedDate);
                            while (t.reviewDates.length < 8) {
                                const last = t.reviewDates[t.reviewDates.length - 1] || t.studiedDate;
                                t.reviewDates.push(addDays(last, 30));
                            }
                            if (!t.topicTab) t.topicTab = inferTopicTab(t.name);
                            ensureTopicTab(t.topicTab);
                            topics.push(t);
                            imported++;
                        }
                    });
                    save();
                    render();
                    showToast(`Imported ${imported} topic${imported !== 1 ? 's' : ''}`, 'success');
                } else {
                    showToast('Invalid file format', 'error');
                }
            } catch (err) {
                console.error('Import error:', err);
                showToast('Failed to parse import file', 'error');
            }
        };
        reader.readAsText(file);
    }

    // ──── Modals ────
    function openResetModal(topicId) {
        const topic = topics.find(t => t.id === topicId);
        if (!topic) return;

        resetTargetId = topicId;
        document.getElementById('reset-topic-name').textContent = topic.name;
        document.getElementById('reset-modal').style.display = '';
    }

    function closeResetModal() {
        resetTargetId = null;
        document.getElementById('reset-modal').style.display = 'none';
    }

    function openDeleteModal(topicId) {
        const topic = topics.find(t => t.id === topicId);
        if (!topic) return;

        deleteTargetId = topicId;
        document.getElementById('delete-topic-name').textContent = topic.name;
        document.getElementById('delete-modal').style.display = '';
    }

    function closeDeleteModal() {
        deleteTargetId = null;
        document.getElementById('delete-modal').style.display = 'none';
    }

    // ──── Authentication ────
    let isLoginMode = true;

    function openAuthModal() {
        isLoginMode = true;
        updateAuthModalUI();
        document.getElementById('auth-modal').style.display = '';
    }

    function closeAuthModal() {
        document.getElementById('auth-modal').style.display = 'none';
        document.getElementById('auth-form').reset();
    }

    function updateAuthModalUI() {
        const title = document.getElementById('auth-title');
        const subtitle = document.getElementById('auth-subtitle');
        const submitBtn = document.getElementById('btn-submit-auth');
        const switchText = document.getElementById('auth-switch-text');
        const switchBtn = document.getElementById('btn-switch-auth');

        if (isLoginMode) {
            title.textContent = 'Login';
            subtitle.textContent = 'Enter your credentials to sync data across devices';
            submitBtn.textContent = 'Login';
            switchText.textContent = "Don't have an account?";
            switchBtn.textContent = 'Register';
        } else {
            title.textContent = 'Register';
            subtitle.textContent = 'Create an account to sync data across devices';
            submitBtn.textContent = 'Register';
            switchText.textContent = 'Already have an account?';
            switchBtn.textContent = 'Login';
        }
    }

    async function handleAuth(e) {
        e.preventDefault();
        const username = document.getElementById('auth-username').value.trim();
        const password = document.getElementById('auth-password').value;

        if (!username || !password) {
            showToast('Please fill in both username and password', 'error');
            return;
        }

        const endpoint = isLoginMode ? '/login' : '/register';
        const submitBtn = document.getElementById('btn-submit-auth');
        submitBtn.disabled = true;
        submitBtn.textContent = 'Processing...';

        try {
            const result = await apiRequest(endpoint, 'POST', { username, password });
            localStorage.setItem(API_KEY_KEY, result.api_key);
            showToast(isLoginMode ? 'Login successful!' : 'Registration successful!', 'success');
            closeAuthModal();
            updateSyncButton();
            
            // Load data from cloud after successful auth
            await loadFromCloud();
            render();
        } catch (error) {
            showToast(error.message || 'Authentication failed', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = isLoginMode ? 'Login' : 'Register';
        }
    }

    function logout() {
        localStorage.removeItem(API_KEY_KEY);
        showToast('Logged out successfully', 'info');
        updateSyncButton();
        loadFromLocal();
        render();
    }

    // ──── Event Binding ────
    function bindEvents() {
        // Add topic form
        document.getElementById('add-topic-form').addEventListener('submit', (e) => {
            e.preventDefault();
            const nameInput = document.getElementById('topic-input');
            const dateInput = document.getElementById('date-input');
            const name = nameInput.value.trim();
            const date = dateInput.value;

            if (!name || !date) {
                showToast('Please fill in both topic name and study date', 'error');
                return;
            }

            addTopic(name, date);
            nameInput.value = '';
            nameInput.focus();
        });

        // Set default date to today
        document.getElementById('date-input').value = todayStr();

        // Search & filter
        document.getElementById('search-input').addEventListener('input', () => renderTable());
        document.getElementById('filter-select').addEventListener('change', () => renderTable());

        document.getElementById('btn-add-tab').addEventListener('click', () => {
            const name = normalizeTopicTab(prompt('New topic tab name', ''));
            if (!name) return;
            ensureTopicTab(name);
            activeTopicTab = name;
            save();
            render();
            showToast(`"${name}" tab added`, 'success');
        });

        // Mark all due
        document.getElementById('btn-mark-all-due').addEventListener('click', markAllDueComplete);

        // Toggle form
        const formEl = document.getElementById('add-topic-form');
        const toggleBtn = document.getElementById('btn-toggle-form');
        toggleBtn.addEventListener('click', () => {
            const isHidden = formEl.style.display === 'none';
            formEl.style.display = isHidden ? '' : 'none';
            toggleBtn.querySelector('svg').style.transform = isHidden ? '' : 'rotate(180deg)';
        });

        // Authentication modal
        document.getElementById('auth-form').addEventListener('submit', handleAuth);
        document.getElementById('btn-cancel-auth').addEventListener('click', closeAuthModal);
        document.getElementById('btn-switch-auth').addEventListener('click', () => {
            isLoginMode = !isLoginMode;
            updateAuthModalUI();
        });

        // Sync button
        document.getElementById('btn-sync').addEventListener('click', async () => {
            const apiKey = localStorage.getItem(API_KEY_KEY);
            if (apiKey) {
                // If logged in, sync data
                const syncText = document.getElementById('sync-text');
                syncText.textContent = 'Syncing...';
                try {
                    await saveToCloud();
                    await loadFromCloud();
                    render();
                    showToast('Data synced successfully!', 'success');
                } catch (error) {
                    showToast('Sync failed: ' + error.message, 'error');
                } finally {
                    syncText.textContent = 'Sync';
                }
            } else {
                // If not logged in, open auth modal
                openAuthModal();
            }
        });

        // Update sync button text based on auth status
        function updateSyncButton() {
            const syncText = document.getElementById('sync-text');
            const apiKey = localStorage.getItem(API_KEY_KEY);
            syncText.textContent = apiKey ? 'Sync' : 'Login';
        }

        // Export / Import
        document.getElementById('btn-export').addEventListener('click', exportData);
        document.getElementById('btn-theme-toggle').addEventListener('click', toggleTheme);
        document.getElementById('btn-import').addEventListener('click', () => {
            document.getElementById('import-file').click();
        });
        document.getElementById('import-file').addEventListener('change', (e) => {
            if (e.target.files[0]) {
                importData(e.target.files[0]);
                e.target.value = '';
            }
        });

        // Reset modal
        document.getElementById('btn-cancel-reset').addEventListener('click', closeResetModal);
        document.getElementById('btn-confirm-reset').addEventListener('click', () => {
            if (resetTargetId) {
                resetTopic(resetTargetId);
                closeResetModal();
            }
        });
        document.getElementById('reset-modal').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) closeResetModal();
        });

        // Delete modal
        document.getElementById('btn-cancel-delete').addEventListener('click', closeDeleteModal);
        document.getElementById('btn-confirm-delete').addEventListener('click', () => {
            if (deleteTargetId) {
                deleteTopic(deleteTargetId);
                closeDeleteModal();
            }
        });
        document.getElementById('delete-modal').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) closeDeleteModal();
        });

        // Auth modal
        document.getElementById('auth-modal').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) closeAuthModal();
        });

        // Keyboard: Escape to close modals
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeResetModal();
                closeDeleteModal();
            }
        });
    }

    // ──── Init ────
    function init() {
        initTheme();
        load();
        seedIfNeeded();
        bindEvents();
        render();

        // Automatically update highlights and review status when the date changes
        let lastCheckedDate = todayStr();
        setInterval(() => {
            const currentDate = todayStr();
            if (currentDate !== lastCheckedDate) {
                lastCheckedDate = currentDate;
                render();
            }
        }, 60000); // Check every minute
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
