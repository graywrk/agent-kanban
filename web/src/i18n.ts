/**
 * Tiny i18n engine — no external deps.
 *
 * Two locales (ru/en), flat dot-namespace keys, `{param}` interpolation,
 * and a Russian-plural helper for the one plural case in the UI (diff hunks).
 * A subscribe/store layer in i18n.tsx wires this into React.
 */

export type Locale = "ru" | "en";

export const LANGS: { code: Locale; label: string }[] = [
  { code: "ru", label: "RU" },
  { code: "en", label: "EN" },
];

// ── Message catalogs ────────────────────────────────────────────────────────
// Keys are flat dotted strings grouped by feature. English is the source
// catalog; Russian mirrors it 1:1. If a key is missing in the active locale
// we fall back to English, then to the key itself (so a missing translation
// is visible, not invisible).

type Catalog = Record<string, string>;

const en: Catalog = {
  // common
  "common.loading": "Loading…",
  "common.backToBoard": "← Back to board",
  "common.cancel": "Cancel",
  "common.send": "Send",
  "common.add": "Add",
  "common.edit": "Edit",
  "common.close": "Close",
  "common.dismiss": "Dismiss",
  "common.copy": "Copy",
  "common.copied": "Copied",
  "common.never": "never",
  "common.empty": "empty",

  // nav
  "nav.admin": "Admin",
  "nav.logout": "Log out",
  "nav.theme.toLight": "Switch to light",
  "nav.theme.toDark": "Switch to dark",
  "nav.theme.toggle": "Toggle theme",

  // login
  "login.eyebrow.setup": "First run",
  "login.eyebrow.login": "Sign in",
  "login.brand": "Agent Kanban",
  "login.subtitle.setup": "Create the admin account to get started.",
  "login.subtitle.login": "Operator console for pull-based agents.",
  "login.usernameLabel": "Username",
  "login.passwordLabel": "Password",
  "login.confirmLabel": "Confirm password",
  "login.usernamePlaceholder": "username",
  "login.error.shortPassword": "Password must be at least 8 characters",
  "login.error.mismatch": "Passwords do not match",
  "login.error.failed": "Login failed",
  "login.button.setup": "Create admin",
  "login.button.login": "Log in",

  // board
  "board.eyebrow": "Board",
  "board.title": "All tasks",
  "board.newTask": "+ New task",
  "board.tip": "Drag cards between columns. Drop into {ready} to make them available to agents via MCP.",
  "board.tipReady": "READY",

  // column
  "column.empty": "empty",

  // status labels
  "status.todo": "Todo",
  "status.ready": "Ready",
  "status.in_progress": "Active",
  "status.review": "Review",
  "status.done": "Done",
  "status.blocked": "Blocked",
  "status.cancelled": "Cancelled",

  // task card
  "task.live": "live",
  "task.reservedTooltip": "Reserved for {agent}",
  "task.claimedBy": "claimed by {name}",
  "task.pr": "PR #{num}",
  "task.prFallback": "pr",

  // pr status (server values: merged / closed / null=open)
  "pr.merged": "merged",
  "pr.closed": "closed",
  "pr.open": "open",

  // card detail
  "card.back": "← Back to board",
  "card.taskPrefix": "Task #{id}",
  "card.reservedTooltip": "Reserved for this agent",
  "card.section.progress": "Progress",
  "card.section.details": "Details",
  "card.noDescription": "No description",
  "card.assignedTo": "Assigned to",
  "card.assignAnyone": "Anyone (unassigned)",
  "card.assignTooltip": "Reserve this task for a specific agent. Others won't see or claim it.",
  "card.reopenReady": "Reopen → ready",
  "card.cancel": "Cancel",
  "card.error.assign": "Failed to assign task",
  "card.error.update": "Failed to update task",

  // comments
  "comment.heading": "Comments",
  "comment.empty": "No comments yet.",
  "comment.seen": "seen",
  "comment.pending": "pending",
  "comment.inputPlaceholder": "Add a comment for the agent…",
  "comment.statusAfter": "Status after posting",
  "comment.toInProgress": "→ in_progress",
  "comment.toReady": "→ ready",
  "comment.sending": "Sending…",
  "comment.error": "Failed to post comment",

  // new task modal
  "newTask.eyebrow": "New task",
  "newTask.title": "Create a task",
  "newTask.titleLabel": "Title",
  "newTask.titlePlaceholder": "What needs to be done?",
  "newTask.descLabel": "Description",
  "newTask.descPlaceholder": "Markdown supported",
  "newTask.tagsLabel": "Tags",
  "newTask.tagsPlaceholder": "comma-separated",
  "newTask.repoLabel": "Repo path (optional)",
  "newTask.baseLabel": "Base branch (optional)",
  "newTask.assignLabel": "Assign to (optional)",
  "newTask.assignTooltip": "Reserve this task for a specific agent. Others won't see it.",
  "newTask.assignAnyone": "Anyone (unassigned)",
  "newTask.creating": "Creating…",
  "newTask.create": "Create task",
  "newTask.error": "Failed to create task",

  // progress feed
  "progress.collapseAll": "Collapse all diffs",
  "progress.expandAll": "Expand all diffs",
  "progress.diff": "diff",
  "progress.hunks": "{count} hunk(s)",

  // admin
  "admin.eyebrow": "Administration",
  "admin.title": "Tokens & users",
  "admin.tokensHeading": "Tokens (agents)",
  "admin.usersHeading": "Users",
  "admin.banner": "Copy now — shown once",
  "admin.agentPlaceholder": "agent_name (e.g. codex)",
  "admin.descPlaceholder": "description (optional)",
  "admin.mint": "Mint",
  "admin.col.agent": "Agent",
  "admin.col.description": "Description",
  "admin.col.created": "Created",
  "admin.col.lastUsed": "Last used",
  "admin.col.role": "Role",
  "admin.col.username": "Username",
  "admin.noTokens": "No tokens yet.",
  "admin.revoke": "Revoke",
  "admin.userPlaceholder": "username",
  "admin.passPlaceholder": "password",
  "admin.admin": "admin",
  "admin.role.admin": "admin",
  "admin.role.user": "user",
  "admin.changePassBody":
    "Change password — enter {your} current admin password and a new password (8+) for {name}.",
  "admin.changePassYour": "your",
  "admin.yourCurrentPass": "your current password",
  "admin.newPassFor": "new password for {name}",
  "admin.changePassword": "Change password",
  "admin.promote": "Promote to admin",
  "admin.demote": "Demote",
  "admin.deleteUser": "Delete user",
  "admin.error.mint": "Failed to mint token",
  "admin.error.revoke": "Failed to revoke token",
  "admin.error.addUser": "Failed to add user",
  "admin.error.removeUser": "Failed to remove user",
  "admin.error.changePass": "Failed to change password",
  "admin.error.adminFlag": "Failed to update admin flag",
};

const ru: Catalog = {
  // common
  "common.loading": "Загрузка…",
  "common.backToBoard": "← К доске",
  "common.cancel": "Отмена",
  "common.send": "Отправить",
  "common.add": "Добавить",
  "common.edit": "Изменить",
  "common.close": "Закрыть",
  "common.dismiss": "Скрыть",
  "common.copy": "Копировать",
  "common.copied": "Скопировано",
  "common.never": "никогда",
  "common.empty": "пусто",

  // nav
  "nav.admin": "Админка",
  "nav.logout": "Выйти",
  "nav.theme.toLight": "Светлая тема",
  "nav.theme.toDark": "Тёмная тема",
  "nav.theme.toggle": "Сменить тему",

  // login
  "login.eyebrow.setup": "Первый запуск",
  "login.eyebrow.login": "Вход",
  "login.brand": "Agent Kanban",
  "login.subtitle.setup": "Создайте аккаунт администратора для начала работы.",
  "login.subtitle.login": "Панель оператора для pull-агентов.",
  "login.usernameLabel": "Имя пользователя",
  "login.passwordLabel": "Пароль",
  "login.confirmLabel": "Повторите пароль",
  "login.usernamePlaceholder": "username",
  "login.error.shortPassword": "Пароль должен быть не короче 8 символов",
  "login.error.mismatch": "Пароли не совпадают",
  "login.error.failed": "Не удалось войти",
  "login.button.setup": "Создать администратора",
  "login.button.login": "Войти",

  // board
  "board.eyebrow": "Доска",
  "board.title": "Все задачи",
  "board.newTask": "+ Новая задача",
  "board.tip":
    "Перетаскивайте карточки между колонками. Бросьте в {ready}, чтобы сделать их доступными агентам через MCP.",
  "board.tipReady": "READY",

  // column
  "column.empty": "пусто",

  // status labels
  "status.todo": "Очередь",
  "status.ready": "Готово",
  "status.in_progress": "В работе",
  "status.review": "Ревью",
  "status.done": "Готово",
  "status.blocked": "Заблокировано",
  "status.cancelled": "Отменено",

  // task card
  "task.live": "активна",
  "task.reservedTooltip": "Зарезервировано для {agent}",
  "task.claimedBy": "взял {name}",
  "task.pr": "PR #{num}",
  "task.prFallback": "pr",

  // pr status
  "pr.merged": "слит",
  "pr.closed": "закрыт",
  "pr.open": "открыт",

  // card detail
  "card.back": "← К доске",
  "card.taskPrefix": "Задача #{id}",
  "card.reservedTooltip": "Зарезервировано для этого агента",
  "card.section.progress": "Прогресс",
  "card.section.details": "Детали",
  "card.noDescription": "Нет описания",
  "card.assignedTo": "Назначено",
  "card.assignAnyone": "Кому угодно (не назначено)",
  "card.assignTooltip":
    "Зарезервировать задачу за конкретным агентом. Другие не увидят её и не смогут взять.",
  "card.reopenReady": "Переоткрыть → ready",
  "card.cancel": "Отменить",
  "card.error.assign": "Не удалось назначить задачу",
  "card.error.update": "Не удалось обновить задачу",

  // comments
  "comment.heading": "Комментарии",
  "comment.empty": "Комментариев пока нет.",
  "comment.seen": "прочитано",
  "comment.pending": "ожидает",
  "comment.inputPlaceholder": "Комментарий для агента…",
  "comment.statusAfter": "Статус после отправки",
  "comment.toInProgress": "→ in_progress",
  "comment.toReady": "→ ready",
  "comment.sending": "Отправка…",
  "comment.error": "Не удалось отправить комментарий",

  // new task modal
  "newTask.eyebrow": "Новая задача",
  "newTask.title": "Создать задачу",
  "newTask.titleLabel": "Заголовок",
  "newTask.titlePlaceholder": "Что нужно сделать?",
  "newTask.descLabel": "Описание",
  "newTask.descPlaceholder": "Поддерживается Markdown",
  "newTask.tagsLabel": "Теги",
  "newTask.tagsPlaceholder": "через запятую",
  "newTask.repoLabel": "Путь к репозиторию (опц.)",
  "newTask.baseLabel": "Базовая ветка (опц.)",
  "newTask.assignLabel": "Назначить (опц.)",
  "newTask.assignTooltip":
    "Зарезервировать задачу за конкретным агентом. Другие не увидят её.",
  "newTask.assignAnyone": "Кому угодно (не назначено)",
  "newTask.creating": "Создание…",
  "newTask.create": "Создать задачу",
  "newTask.error": "Не удалось создать задачу",

  // progress feed
  "progress.collapseAll": "Свернуть все диффы",
  "progress.expandAll": "Развернуть все диффы",
  "progress.diff": "дифф",
  "progress.hunks": "{count} блок(ов)",

  // admin
  "admin.eyebrow": "Администрирование",
  "admin.title": "Токены и пользователи",
  "admin.tokensHeading": "Токены (агенты)",
  "admin.usersHeading": "Пользователи",
  "admin.banner": "Скопируйте сейчас — показан один раз",
  "admin.agentPlaceholder": "agent_name (напр. codex)",
  "admin.descPlaceholder": "описание (опц.)",
  "admin.mint": "Создать",
  "admin.col.agent": "Агент",
  "admin.col.description": "Описание",
  "admin.col.created": "Создан",
  "admin.col.lastUsed": "Посл. использование",
  "admin.col.role": "Роль",
  "admin.col.username": "Имя",
  "admin.noTokens": "Токенов пока нет.",
  "admin.revoke": "Отозвать",
  "admin.userPlaceholder": "username",
  "admin.passPlaceholder": "password",
  "admin.admin": "admin",
  "admin.role.admin": "админ",
  "admin.role.user": "пользователь",
  "admin.changePassBody":
    "Смена пароля — введите {your} текущий пароль администратора и новый пароль (8+) для {name}.",
  "admin.changePassYour": "свой",
  "admin.yourCurrentPass": "ваш текущий пароль",
  "admin.newPassFor": "новый пароль для {name}",
  "admin.changePassword": "Сменить пароль",
  "admin.promote": "Повысить до админа",
  "admin.demote": "Понизить",
  "admin.deleteUser": "Удалить пользователя",
  "admin.error.mint": "Не удалось создать токен",
  "admin.error.revoke": "Не удалось отозвать токен",
  "admin.error.addUser": "Не удалось добавить пользователя",
  "admin.error.removeUser": "Не удалось удалить пользователя",
  "admin.error.changePass": "Не удалось сменить пароль",
  "admin.error.adminFlag": "Не удалось изменить права администратора",
};

const CATALOGS: Record<Locale, Catalog> = { en, ru };

// ── Store ───────────────────────────────────────────────────────────────────

const STORAGE_KEY = "kanban-locale";

let _locale: Locale = getInitialLocale();
const _listeners = new Set<(l: Locale) => void>();

/** Resolve the initial locale: saved pref → browser language → en. */
export function getInitialLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "ru" || saved === "en") return saved;
  } catch {
    /* localStorage unavailable */
  }
  if (typeof navigator !== "undefined" && navigator.language?.toLowerCase().startsWith("ru")) {
    return "ru";
  }
  return "en";
}

export function getLocale(): Locale {
  return _locale;
}

export function setLocale(next: Locale): void {
  if (next === _locale) return;
  _locale = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* ignore */
  }
  if (typeof document !== "undefined") {
    document.documentElement.lang = next;
  }
  for (const fn of _listeners) fn(next);
}

export function subscribe(fn: (l: Locale) => void): () => void {
  _listeners.add(fn);
  return () => _listeners.delete(fn);
}

// ── Translation functions ───────────────────────────────────────────────────

/** Translate `key`, interpolating `{param}` tokens from `params`. */
export function t(key: string, params?: Record<string, string | number>): string {
  const cat = CATALOGS[_locale] ?? en;
  let raw = cat[key] ?? en[key] ?? key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      raw = raw.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
    }
  }
  return raw;
}

/**
 * Pluralized translate. Russian has three forms (1 / 2–4 / 5+); English is
 * handled by the catalog's `{count}` token with an explicit "(s)" suffix.
 * We special-case the single plural key (`progress.hunks`) via a RU override.
 */
export function tCount(key: string, count: number): string {
  if (_locale === "ru") {
    const mod10 = count % 10;
    const mod100 = count % 100;
    let suffix: string;
    if (mod10 === 1 && mod100 !== 11) suffix = "";
    else if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) suffix = "а";
    else suffix = "ов";
    // For progress.hunks: "{count} блок(ов)" → replace the (ов) variant.
    if (key === "progress.hunks") {
      return `${count} блок${suffix}`;
    }
  }
  return t(key, { count });
}

/** Map our locale to a BCP-47 tag for Intl APIs (toLocaleString etc.). */
export function localeBcp47(locale: Locale = _locale): string {
  return locale === "ru" ? "ru-RU" : "en-US";
}
