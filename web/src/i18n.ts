/**
 * Tiny i18n engine — no external deps.
 *
 * Three locales (ru/en/sv), flat dot-namespace keys, `{param}` interpolation,
 * and a Russian-plural helper for the one plural case in the UI (diff hunks).
 * A subscribe/store layer in i18n.tsx wires this into React.
 */

export type Locale = "ru" | "en" | "sv";

export const LANGS: { code: Locale; label: string }[] = [
  { code: "ru", label: "RU" },
  { code: "en", label: "EN" },
  { code: "sv", label: "SV" },
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
  "board.allProjects": "All projects",
  "board.projectFilterTooltip": "Show tasks for one project",

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
  "task.createdTooltip": "Created {date}",
  "task.preferredTooltip": "Preferred agent: {agent}",
  "task.pr": "PR #{num}",
  "task.prFallback": "pr",

  // pr status (server values: merged / closed / null=open)
  "pr.merged": "merged",
  "pr.closed": "closed",
  "pr.open": "open",

  // priority
  "priority.critical": "Critical",
  "priority.high": "High",
  "priority.medium": "Medium",
  "priority.low": "Low",

  // card detail
  "card.back": "← Back to board",
  "card.taskPrefix": "Task #{id}",
  "card.reservedTooltip": "Reserved for this agent",
  "card.section.progress": "Progress",
  "card.section.details": "Details",
  "card.noDescription": "No description",
  "card.created": "Created",
  "card.createdBy": "by {name}",
  "card.assignedTo": "Assigned to",
  "card.assignAnyone": "Anyone (unassigned)",
  "card.assignTooltip": "Reserve this task for a specific agent. Others won't see or claim it.",
  "card.priority": "Priority",
  "card.preferredModel": "Preferred model",
  "card.preferredNone": "No preference",
  "card.preferredTooltip": "Soft hint: this agent sees the task first in get_next_task, others can still claim it.",
  "card.project": "Project",
  "card.projectNone": "No project",
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
  "newTask.projectLabel": "Project (optional)",
  "newTask.projectNone": "No project",
  "newTask.priorityLabel": "Priority",
  "newTask.preferredLabel": "Preferred model (optional)",
  "newTask.preferredNone": "No preference",
  "newTask.preferredTooltip": "Soft hint: this agent sees the task first, others can still claim it.",
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
  "admin.projectsHeading": "Projects",
  "admin.usersHeading": "Users",
  "admin.projectNamePlaceholder": "project name",
  "admin.projectRepoPlaceholder": "repo path (optional)",
  "admin.projectBranchPlaceholder": "default branch (optional)",
  "admin.col.projectName": "Project",
  "admin.col.projectRepo": "Repo path",
  "admin.col.projectBranch": "Default branch",
  "admin.noProjects": "No projects yet.",
  "admin.error.addProject": "Failed to add project",
  "admin.error.updateProject": "Failed to update project",
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
  "board.allProjects": "Все проекты",
  "board.projectFilterTooltip": "Показать задачи одного проекта",

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
  "task.createdTooltip": "Создано {date}",
  "task.preferredTooltip": "Предпочтительный агент: {agent}",
  "task.pr": "PR #{num}",
  "task.prFallback": "pr",

  // pr status
  "pr.merged": "слит",
  "pr.closed": "закрыт",
  "pr.open": "открыт",

  // priority
  "priority.critical": "Критично",
  "priority.high": "Высокий",
  "priority.medium": "Средний",
  "priority.low": "Низкий",

  // card detail
  "card.back": "← К доске",
  "card.taskPrefix": "Задача #{id}",
  "card.reservedTooltip": "Зарезервировано для этого агента",
  "card.section.progress": "Прогресс",
  "card.section.details": "Детали",
  "card.noDescription": "Нет описания",
  "card.created": "Создано",
  "card.createdBy": "автор {name}",
  "card.assignedTo": "Назначено",
  "card.assignAnyone": "Кому угодно (не назначено)",
  "card.assignTooltip":
    "Зарезервировать задачу за конкретным агентом. Другие не увидят её и не смогут взять.",
  "card.priority": "Приоритет",
  "card.preferredModel": "Предпочтительная модель",
  "card.preferredNone": "Без предпочтения",
  "card.preferredTooltip":
    "Мягкий намёк: этот агент увидит задачу первой в get_next_task, остальные всё ещё могут её взять.",
  "card.project": "Проект",
  "card.projectNone": "Без проекта",
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
  "newTask.projectLabel": "Проект (опц.)",
  "newTask.projectNone": "Без проекта",
  "newTask.priorityLabel": "Приоритет",
  "newTask.preferredLabel": "Предпочтительная модель (опц.)",
  "newTask.preferredNone": "Без предпочтения",
  "newTask.preferredTooltip":
    "Мягкий намёк: этот агент увидит задачу первой, остальные всё ещё могут её взять.",
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
  "admin.projectsHeading": "Проекты",
  "admin.usersHeading": "Пользователи",
  "admin.projectNamePlaceholder": "название проекта",
  "admin.projectRepoPlaceholder": "путь к репозиторию (опц.)",
  "admin.projectBranchPlaceholder": "ветка по умолчанию (опц.)",
  "admin.col.projectName": "Проект",
  "admin.col.projectRepo": "Путь к репозиторию",
  "admin.col.projectBranch": "Ветка по умолчанию",
  "admin.noProjects": "Проектов пока нет.",
  "admin.error.addProject": "Не удалось добавить проект",
  "admin.error.updateProject": "Не удалось обновить проект",
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

const sv: Catalog = {
  // common
  "common.loading": "Laddar…",
  "common.backToBoard": "← Tillbaka till tavlan",
  "common.cancel": "Avbryt",
  "common.send": "Skicka",
  "common.add": "Lägg till",
  "common.edit": "Ändra",
  "common.close": "Stäng",
  "common.dismiss": "Dölj",
  "common.copy": "Kopiera",
  "common.copied": "Kopierat",
  "common.never": "aldrig",
  "common.empty": "tom",

  // nav
  "nav.admin": "Admin",
  "nav.logout": "Logga ut",
  "nav.theme.toLight": "Byt till ljust",
  "nav.theme.toDark": "Byt till mörkt",
  "nav.theme.toggle": "Byt tema",

  // login
  "login.eyebrow.setup": "Första starten",
  "login.eyebrow.login": "Logga in",
  "login.brand": "Agent Kanban",
  "login.subtitle.setup": "Skapa administratörskontot för att komma igång.",
  "login.subtitle.login": "Operatörskonsol för pull-baserade agenter.",
  "login.usernameLabel": "Användarnamn",
  "login.passwordLabel": "Lösenord",
  "login.confirmLabel": "Upprepa lösenord",
  "login.usernamePlaceholder": "användarnamn",
  "login.error.shortPassword": "Lösenordet måste vara minst 8 tecken",
  "login.error.mismatch": "Lösenorden är inte lika",
  "login.error.failed": "Inloggningen misslyckades",
  "login.button.setup": "Skapa administratör",
  "login.button.login": "Logga in",

  // board
  "board.eyebrow": "Tavla",
  "board.title": "Alla uppgifter",
  "board.newTask": "+ Ny uppgift",
  "board.tip":
    "Dra kort mellan kolumnerna. Släpp i {ready} för att göra dem tillgängliga för agenter via MCP.",
  "board.tipReady": "READY",
  "board.allProjects": "Alla projekt",
  "board.projectFilterTooltip": "Visa uppgifter för ett projekt",

  // column
  "column.empty": "tom",

  // status labels
  "status.todo": "Att göra",
  "status.ready": "Klar",
  "status.in_progress": "Pågår",
  "status.review": "Granskning",
  "status.done": "Klar",
  "status.blocked": "Blockerad",
  "status.cancelled": "Avbruten",

  // task card
  "task.live": "live",
  "task.reservedTooltip": "Reserverad för {agent}",
  "task.claimedBy": "tagen av {name}",
  "task.createdTooltip": "Skapad {date}",
  "task.preferredTooltip": "Föredragen agent: {agent}",
  "task.pr": "PR #{num}",
  "task.prFallback": "pr",

  // pr status
  "pr.merged": "sammanslagen",
  "pr.closed": "stängd",
  "pr.open": "öppen",

  // priority
  "priority.critical": "Kritisk",
  "priority.high": "Hög",
  "priority.medium": "Medium",
  "priority.low": "Låg",

  // card detail
  "card.back": "← Tillbaka till tavlan",
  "card.taskPrefix": "Uppgift #{id}",
  "card.reservedTooltip": "Reserverad för den här agenten",
  "card.section.progress": "Förlopp",
  "card.section.details": "Detaljer",
  "card.noDescription": "Ingen beskrivning",
  "card.created": "Skapad",
  "card.createdBy": "av {name}",
  "card.assignedTo": "Tilldelad",
  "card.assignAnyone": "Vem som helst (ej tilldelad)",
  "card.assignTooltip":
    "Reservera uppgiften för en specifik agent. Andra ser den inte och kan inte ta den.",
  "card.priority": "Prioritet",
  "card.preferredModel": "Föredragen modell",
  "card.preferredNone": "Ingen preferens",
  "card.preferredTooltip":
    "Mjuk preferens: agenten ser uppgiften först i get_next_task, andra kan fortfarande ta den.",
  "card.project": "Projekt",
  "card.projectNone": "Inget projekt",
  "card.reopenReady": "Öppna igen → ready",
  "card.cancel": "Avbryt",
  "card.error.assign": "Kunde inte tilldela uppgiften",
  "card.error.update": "Kunde inte uppdatera uppgiften",

  // comments
  "comment.heading": "Kommentarer",
  "comment.empty": "Inga kommentarer än.",
  "comment.seen": "läst",
  "comment.pending": "oläst",
  "comment.inputPlaceholder": "Lämna en kommentar till agenten…",
  "comment.statusAfter": "Status efter att kommentaren skickats",
  "comment.toInProgress": "→ in_progress",
  "comment.toReady": "→ ready",
  "comment.sending": "Skickar…",
  "comment.error": "Kunde inte skicka kommentaren",

  // new task modal
  "newTask.eyebrow": "Ny uppgift",
  "newTask.title": "Skapa en uppgift",
  "newTask.titleLabel": "Titel",
  "newTask.titlePlaceholder": "Vad behöver göras?",
  "newTask.descLabel": "Beskrivning",
  "newTask.descPlaceholder": "Markdown stöds",
  "newTask.tagsLabel": "Taggar",
  "newTask.tagsPlaceholder": "kommaseparerade",
  "newTask.projectLabel": "Projekt (valfritt)",
  "newTask.projectNone": "Inget projekt",
  "newTask.priorityLabel": "Prioritet",
  "newTask.preferredLabel": "Föredragen modell (valfritt)",
  "newTask.preferredNone": "Ingen preferens",
  "newTask.preferredTooltip":
    "Mjuk preferens: agenten ser uppgiften först, andra kan fortfarande ta den.",
  "newTask.repoLabel": "Reposökväg (valfritt)",
  "newTask.baseLabel": "Basbranch (valfritt)",
  "newTask.assignLabel": "Tilldela (valfritt)",
  "newTask.assignTooltip":
    "Reservera uppgiften för en specifik agent. Andra ser den inte.",
  "newTask.assignAnyone": "Vem som helst (ej tilldelad)",
  "newTask.creating": "Skapar…",
  "newTask.create": "Skapa uppgift",
  "newTask.error": "Kunde inte skapa uppgiften",

  // progress feed
  "progress.collapseAll": "Fäll ihop alla diffar",
  "progress.expandAll": "Fäll ut alla diffar",
  "progress.diff": "diff",
  "progress.hunks": "{count} block",

  // admin
  "admin.eyebrow": "Administration",
  "admin.title": "Token och användare",
  "admin.tokensHeading": "Token (agenter)",
  "admin.projectsHeading": "Projekt",
  "admin.usersHeading": "Användare",
  "admin.projectNamePlaceholder": "projektnamn",
  "admin.projectRepoPlaceholder": "reposökväg (valfritt)",
  "admin.projectBranchPlaceholder": "standardbranch (valfritt)",
  "admin.col.projectName": "Projekt",
  "admin.col.projectRepo": "Reposökväg",
  "admin.col.projectBranch": "Standardbranch",
  "admin.noProjects": "Inga projekt än.",
  "admin.error.addProject": "Kunde inte lägga till projektet",
  "admin.error.updateProject": "Kunde inte uppdatera projektet",
  "admin.banner": "Kopiera nu, visas en enda gång",
  "admin.agentPlaceholder": "agent_name (t.ex. codex)",
  "admin.descPlaceholder": "beskrivning (valfritt)",
  "admin.mint": "Skapa",
  "admin.col.agent": "Agent",
  "admin.col.description": "Beskrivning",
  "admin.col.created": "Skapad",
  "admin.col.lastUsed": "Senast använt",
  "admin.col.role": "Roll",
  "admin.col.username": "Användarnamn",
  "admin.noTokens": "Inga token än.",
  "admin.revoke": "Upphör",
  "admin.userPlaceholder": "användarnamn",
  "admin.passPlaceholder": "lösenord",
  "admin.admin": "admin",
  "admin.role.admin": "admin",
  "admin.role.user": "användare",
  "admin.changePassBody":
    "Byt lösenord, ange {your} nuvarande administratörslösenord och ett nytt lösenord (8+) för {name}.",
  "admin.changePassYour": "ditt",
  "admin.yourCurrentPass": "ditt nuvarande lösenord",
  "admin.newPassFor": "nytt lösenord för {name}",
  "admin.changePassword": "Byt lösenord",
  "admin.promote": "Befordra till admin",
  "admin.demote": "Nedgradera",
  "admin.deleteUser": "Ta bort användaren",
  "admin.error.mint": "Kunde inte skapa token",
  "admin.error.revoke": "Kunde inte upphäva token",
  "admin.error.addUser": "Kunde inte lägga till användaren",
  "admin.error.removeUser": "Kunde inte ta bort användaren",
  "admin.error.changePass": "Kunde inte byta lösenord",
  "admin.error.adminFlag": "Kunde inte ändra administratörsrättigheterna",
};

const CATALOGS: Record<Locale, Catalog> = { en, ru, sv };

// ── Store ───────────────────────────────────────────────────────────────────

const STORAGE_KEY = "kanban-locale";

let _locale: Locale = getInitialLocale();
const _listeners = new Set<(l: Locale) => void>();

/** Resolve the initial locale: saved pref → browser language → en. */
export function getInitialLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "ru" || saved === "en" || saved === "sv") return saved;
  } catch {
    /* localStorage unavailable */
  }
  if (typeof navigator !== "undefined") {
    const lang = navigator.language?.toLowerCase() ?? "";
    if (lang.startsWith("ru")) return "ru";
    if (lang.startsWith("sv")) return "sv";
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
  if (locale === "ru") return "ru-RU";
  if (locale === "sv") return "sv-SE";
  return "en-US";
}
