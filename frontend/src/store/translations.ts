export interface TranslationSchema {
  common: {
    cancel: string;
    create: string;
    save: string;
    close: string;
    active: string;
    paused: string;
    warning: string;
    cooldown: string;
    exhausted: string;
    error: string;
    degraded: string;
    reauth_required: string;
    disabled: string;
    high: string;
    medium: string;
    low: string;
    managed: string;
    byo: string;
    logout: string;
    unlimited: string;
    delete_action: string;
    refresh: string;
  };
  layout: {
    overview: string;
    keys: string;
    credentials: string;
    logs: string;
    console_title: string;
    overview_title: string;
    keys_title: string;
    credentials_title: string;
    logs_title: string;
    theme_light: string;
    theme_dark: string;
  };
  login: {
    title: string;
    desc: string;
    btn_google: string;
    btn_mock: string;
    footer: string;
    dev_mode_title: string;
    dev_mode_desc: string;
    token_placeholder: string;
    btn_token: string;
    error_invalid_token: string;
    error_rate_limited: string;
    error_generic: string;
  };
  overview: {
    desc: string;
    active_pools: string;
    active_pools_desc: string;
    active_keys: string;
    active_keys_desc: string;
    success_rate: string;
    success_rate_desc: string;
    total_tokens: string;
    total_tokens_desc: string;
    total_requests: string;
    total_requests_desc: string;
    chart_title: string;
    chart_desc: string;
    health_title: string;
    col_name: string;
    col_status: string;
    col_quota: string;
    status_ok: string;
    status_degraded: string;
    strip_accounts: string;
    strip_active: string;
    strip_success: string;
  };
  keys: {
    title: string;
    desc: string;
    btn_create: string;
    btn_cancel: string;
    form_title: string;
    form_name: string;
    form_quota: string;
    form_rpm: string;
    form_btn: string;
    col_name: string;
    col_status: string;
    col_usage: string;
    col_rpm: string;
    col_actions: string;
    usage_tokens: string;
    tokens_suffix: string;
    aria_save: string;
    aria_cancel: string;
    aria_edit: string;
    aria_pause: string;
    aria_resume: string;
    created_title: string;
    created_desc: string;
    btn_copy: string;
    copied: string;
    btn_done: string;
    confirm_delete: string;
    placeholder_unlimited: string;
    btn_delete: string;
  };
  credentials: {
    title: string;
    desc: string;
    btn_add: string;
    btn_cancel: string;
    form_title: string;
    form_name: string;
    form_provider: string;
    form_type: string;
    form_priority: string;
    form_weight: string;
    form_concurrency: string;
    form_details: string;
    form_details_placeholder: string;
    form_name_placeholder: string;
    form_btn: string;
    option_byo: string;
    option_managed: string;
    col_id: string;
    col_provider: string;
    col_type: string;
    col_priority_weight: string;
    col_status: string;
    tag_managed: string;
    tag_byo: string;
    tier_weight: string;
    lbl_requests: string;
    lbl_latency: string;
    lbl_errors: string;
    lbl_controls: string;
    lbl_priority: string;
    lbl_weight: string;
    lbl_concurrency: string;
    lbl_manual_state: string;
    lbl_json_spec: string;
    btn_save_settings: string;
    btn_close: string;
    latency_suffix: string;
    latency_na: string;
    lbl_connection_method: string;
    option_auto_oauth: string;
    option_manual_sdk: string;
    manual_sdk_instructions_title: string;
    manual_sdk_instruction_1: string;
    manual_sdk_instruction_2: string;
    manual_sdk_instruction_3: string;
    manual_sdk_instruction_4: string;
    lbl_authorize_link: string;
    placeholder_code_or_url: string;
    btn_connect_sdk: string;
    msg_connecting: string;
    lbl_advanced: string;
    form_api_key: string;
    form_base_url: string;
    btn_refresh_quotas: string;
    btn_connect_google: string;
    btn_delete: string;
    confirm_delete: string;
    lbl_token_quota: string;
    lbl_reset_window: string;
    lbl_reset_window_short: string;
    lbl_supported_models: string;
    lbl_models_short: string;
    lbl_remaining: string;
    lbl_usage_limits: string;
    btn_show_model_quotas: string;
    btn_hide_model_quotas: string;
    lbl_no_models: string;
  };
  logs: {
    title: string;
    desc: string;
    btn_simulate: string;
    btn_clear: string;
    col_time: string;
    col_key: string;
    col_pool: string;
    col_model: string;
    col_latency: string;
    col_tokens: string;
    col_cost: string;
    col_response: string;
    empty_state: string;
    tokens_format: string;
    test_modal_title: string;
    lbl_select_model: string;
    lbl_prompt: string;
    placeholder_prompt: string;
    btn_send: string;
    btn_sending: string;
    lbl_response: string;
    lbl_tokens: string;
    lbl_latency: string;
    msg_no_active_creds: string;
    err_rate_limit: string;
    err_unauthorized: string;
    err_unavailable: string;
    msg_executing: string;
    msg_error: string;
    msg_empty_response: string;
  };
  mock: {
    "Antigravity OpenAI Enterprise": string;
    "BYO Anthropic Production": string;
    "BYO OpenAI Backup": string;
    "BYO Cohere Command": string;
    "BYO OpenAI Legacy": string;
    "Antigravity Gemini Flash": string;
    "sk-lev-prod-core": string;
    "sk-lev-dev-sandbox": string;
    "sk-lev-marketing-ai": string;
    "sk-lev-stg-test": string;
  };
}

export const translations: Record<"en" | "ru", TranslationSchema> = {
  en: {
    common: {
      cancel: "Cancel",
      create: "Create",
      save: "Save",
      close: "Close",
      active: "Active",
      paused: "Paused",
      warning: "Warning",
      cooldown: "Cooldown",
      exhausted: "Exhausted",
      error: "Error",
      degraded: "Degraded",
      reauth_required: "Reauth required",
      disabled: "Disabled",
      high: "High",
      medium: "Medium",
      low: "Low",
      managed: "Managed",
      byo: "BYO",
      logout: "Sign Out",
      unlimited: "Unlimited",
      delete_action: "Delete",
      refresh: "Refresh"
    },
    layout: {
      overview: "Overview",
      keys: "API Keys",
      credentials: "AI Accounts",
      logs: "API Logs",
      console_title: "Levitate / Console",
      overview_title: "Overview",
      keys_title: "API Keys",
      credentials_title: "AI Accounts",
      logs_title: "API Logs",
      theme_light: "Light",
      theme_dark: "Dark"
    },
    login: {
      title: "Sign in to Levitate",
      desc: "An easy-to-use proxy gateway for managing your AI models and budgets.",
      btn_google: "Continue with Google",
      btn_mock: "Developer Login",
      footer: "Secure admin console access",
      dev_mode_title: "Local Development Mode",
      dev_mode_desc: "Google OAuth keys are not set. Use developer mock login to access dashboard.",
      token_placeholder: "Enter Admin Token",
      btn_token: "Login with Token",
      error_invalid_token: "Invalid admin token.",
      error_rate_limited: "Too many login attempts. Please try again later.",
      error_generic: "An error occurred during authentication."
    },
    overview: {
      desc: "System overview, active pools and keys performance.",
      active_pools: "Active Accounts",
      active_pools_desc: "active",
      active_keys: "Active API Keys",
      active_keys_desc: "active",
      success_rate: "Success Rate",
      success_rate_desc: "over the last 24 hours",
      total_tokens: "Tokens Consumed",
      total_tokens_desc: "month-over-month",
      total_requests: "Total Requests",
      total_requests_desc: "processed by the gateway",
      chart_title: "API Usage Chart",
      chart_desc: "Monitor the volume of tokens processed by the gateway in real-time.",
      health_title: "Upstream Account Status",
      col_name: "Account Name",
      col_status: "Status",
      col_quota: "Quota Left",
      status_ok: "All systems operational",
      status_degraded: "Degraded performance",
      strip_accounts: "Accounts:",
      strip_active: "active",
      strip_success: "Success"
    },
    keys: {
      title: "API Keys",
      desc: "Create virtual keys for your applications and set limits to control your budget.",
      btn_create: "Create Key",
      btn_cancel: "Cancel",
      form_title: "Create API Key",
      form_name: "Key Name",
      form_quota: "Monthly Budget Limit",
      form_rpm: "Speed Limit (Requests per min)",
      form_btn: "Generate Key",
      col_name: "Key Name",
      col_status: "Status",
      col_usage: "Monthly Quota Usage",
      col_rpm: "Rate Limit (RPM)",
      col_actions: "Actions",
      usage_tokens: "tokens",
      tokens_suffix: "tokens",
      aria_save: "Save changes",
      aria_cancel: "Cancel editing",
      aria_edit: "Edit budget rules",
      aria_pause: "Pause key",
      aria_resume: "Resume key",
      created_title: "API Key Generated Successfully",
      created_desc: "For security reasons, this key will only be shown once. Please copy it immediately.",
      btn_copy: "Copy",
      copied: "Copied!",
      btn_done: "Done",
      confirm_delete: "Are you sure you want to delete the API key",
      placeholder_unlimited: "0 or empty for unlimited",
      btn_delete: "Delete key"
    },
    credentials: {
      title: "AI Provider Accounts",
      desc: "Connect your own AI accounts or use managed providers. We automatically distribute the load to save money and handle errors.",
      btn_add: "Add Account",
      btn_cancel: "Cancel",
      form_title: "Connect Account",
      form_name: "Account Name",
      form_provider: "AI Provider",
      form_type: "Account Type",
      form_priority: "Priority (1 = Highest)",
      form_weight: "Routing Weight",
      form_concurrency: "Max Parallel Requests",
      form_details: "API Details (JSON, Optional)",
      form_details_placeholder: '{\n  "api_key": "your-key-here"\n}',
      form_name_placeholder: "e.g. My OpenAI Account",
      form_btn: "Connect Account",
      option_byo: "My own API key",
      option_managed: "Google Account (Gemini)",
      col_id: "Account",
      col_provider: "Provider",
      col_type: "Type",
      col_priority_weight: "Priority & Weight",
      col_status: "Status",
      tag_managed: "Google",
      tag_byo: "Own Key",
      tier_weight: "Priority {priority} (weight: {weight})",
      lbl_requests: "Total Requests",
      lbl_latency: "Avg Response Time",
      lbl_errors: "Errors",
      lbl_controls: "Configure Routing",
      lbl_priority: "Priority",
      lbl_weight: "Weight",
      lbl_concurrency: "Parallel Limit",
      lbl_manual_state: "Manual Health Override",
      lbl_json_spec: "CONFIGURATION",
      btn_save_settings: "Save Changes",
      btn_close: "Close",
      latency_suffix: " ms",
      latency_na: "N/A",
      lbl_connection_method: "Connection Method",
      option_auto_oauth: "Automatic (Requires GCP Project setup)",
      option_manual_sdk: "Manual (Uses Official Google Client — No GCP setup needed)",
      manual_sdk_instructions_title: "How to connect without GCP Project setup:",
      manual_sdk_instruction_1: "Click the link below to open Google's Consent screen.",
      manual_sdk_instruction_2: "Sign in with your Google account and grant permissions.",
      manual_sdk_instruction_3: "When redirected to localhost (which will fail to load — that's normal), copy the entire URL from the browser's address bar.",
      manual_sdk_instruction_4: "Paste that URL (or the 'code' parameter) in the field below and click Save.",
      lbl_authorize_link: "Authorize Google Account",
      placeholder_code_or_url: "Paste redirect URL or authorization code here",
      btn_connect_sdk: "Connect via Code",
      msg_connecting: "Connecting and verifying quotas...",
      lbl_advanced: "Advanced",
      form_api_key: "API Key",
      form_base_url: "Base URL (Optional)",
      btn_refresh_quotas: "Refresh Quotas",
      btn_connect_google: "Connect Google",
      btn_delete: "Delete",
      confirm_delete: "Are you sure you want to delete this account?",
      lbl_token_quota: "Token Quota",
      lbl_reset_window: "Reset Window (seconds)",
      lbl_reset_window_short: "Reset Window (sec.)",
      lbl_supported_models: "Supported Models (comma-separated)",
      lbl_models_short: "Models (comma-separated)",
      lbl_remaining: "Remaining:",
      lbl_usage_limits: "Antigravity Usage Limits",
      btn_show_model_quotas: "Show Model Quotas",
      btn_hide_model_quotas: "Hide Model Quotas",
      lbl_no_models: "No models configured"
    },
    logs: {
      title: "API Logs",
      desc: "Real-time list of all requests processed by the gateway.",
      btn_simulate: "Send Test Request",
      btn_clear: "Clear Logs",
      col_time: "Time",
      col_key: "API Key",
      col_pool: "Account Used",
      col_model: "Model",
      col_latency: "Response Time",
      col_tokens: "Tokens",
      col_cost: "Cost",
      col_response: "Result",
      empty_state: "No requests yet. Click \"Send Test Request\" to try it out.",
      tokens_format: "{prompt}p / {completion}c",
      test_modal_title: "Test Request",
      lbl_select_model: "Select Model",
      lbl_prompt: "User Message (Prompt)",
      placeholder_prompt: "Enter your prompt...",
      btn_send: "Send Request",
      btn_sending: "Sending...",
      lbl_response: "Model Response",
      lbl_tokens: "Tokens Used",
      lbl_latency: "Latency",
      msg_no_active_creds: "You need at least one active AI account to send requests.",
      err_rate_limit: "429 Rate Limit",
      err_unauthorized: "401 Unauthorized",
      err_unavailable: "503 Service Unavailable",
      msg_executing: "Executing request on upstream AI...",
      msg_error: "Error occurred:",
      msg_empty_response: "[Empty Response]"
    },
    mock: {
      "Antigravity OpenAI Enterprise": "Antigravity OpenAI Enterprise",
      "BYO Anthropic Production": "BYO Anthropic Production",
      "BYO OpenAI Backup": "BYO OpenAI Backup",
      "BYO Cohere Command": "BYO Cohere Command",
      "BYO OpenAI Legacy": "BYO OpenAI Legacy",
      "Antigravity Gemini Flash": "Antigravity Gemini Flash",
      "sk-lev-prod-core": "sk-lev-prod-core",
      "sk-lev-dev-sandbox": "sk-lev-dev-sandbox",
      "sk-lev-marketing-ai": "sk-lev-marketing-ai",
      "sk-lev-stg-test": "sk-lev-stg-test"
    }
  },
  ru: {
    common: {
      cancel: "Отмена",
      create: "Создать",
      save: "Сохранить",
      close: "Закрыть",
      active: "Активен",
      paused: "На паузе",
      warning: "Предупреждение",
      cooldown: "Ожидание",
      exhausted: "Исчерпан",
      error: "Ошибка",
      degraded: "Снижен",
      reauth_required: "Нужна реавторизация",
      disabled: "Отключён",
      high: "Высокий",
      medium: "Средний",
      low: "Низкий",
      managed: "Google",
      byo: "BYO",
      logout: "Выйти",
      unlimited: "Без лимита",
      delete_action: "Удалить",
      refresh: "Обновить"
    },
    layout: {
      overview: "Обзор",
      keys: "API-ключи",
      credentials: "Аккаунты нейросетей",
      logs: "История запросов",
      console_title: "Levitate / Консоль",
      overview_title: "Обзор",
      keys_title: "API-ключи",
      credentials_title: "Аккаунты нейросетей",
      logs_title: "История запросов",
      theme_light: "Светлая",
      theme_dark: "Тёмная"
    },
    login: {
      title: "Вход в Levitate",
      desc: "Прокси-шлюз для управления API-ключами и бюджетом на ИИ.",
      btn_google: "Продолжить через Google",
      btn_mock: "Вход для разработчиков",
      footer: "Безопасный доступ к панели управления",
      dev_mode_title: "Режим локальной разработки",
      dev_mode_desc: "Ключи Google OAuth не настроены. Используйте вход для разработчиков.",
      token_placeholder: "Введите токен администратора",
      btn_token: "Войти по токену",
      error_invalid_token: "Неверный токен администратора.",
      error_rate_limited: "Слишком много попыток входа. Пожалуйста, попробуйте позже.",
      error_generic: "Произошла ошибка при авторизации."
    },
    overview: {
      desc: "Сводка по системе: состояние аккаунтов, ключей и лимитов.",
      active_pools: "Активные аккаунты",
      active_pools_desc: "активно",
      active_keys: "Активные API-ключи",
      active_keys_desc: "активно",
      success_rate: "Успешность",
      success_rate_desc: "за последние 24 часа",
      total_tokens: "Потрачено токенов",
      total_tokens_desc: "к прошлому месяцу",
      total_requests: "Всего запросов",
      total_requests_desc: "обработано шлюзом",
      chart_title: "График использования",
      chart_desc: "Мониторинг токенов, обработанных шлюзом, в реальном времени.",
      health_title: "Статус подключённых аккаунтов",
      col_name: "Название аккаунта",
      col_status: "Статус",
      col_quota: "Остаток квоты",
      status_ok: "Все системы работают штатно",
      status_degraded: "Снижение производительности",
      strip_accounts: "Аккаунты:",
      strip_active: "активно",
      strip_success: "Успех"
    },
    keys: {
      title: "API-ключи",
      desc: "Создавайте виртуальные ключи для приложений и задавайте лимиты расходов.",
      btn_create: "Создать ключ",
      btn_cancel: "Отмена",
      form_title: "Новый API-ключ",
      form_name: "Название ключа",
      form_quota: "Лимит токенов в месяц",
      form_rpm: "Лимит запросов в минуту (RPM)",
      form_btn: "Сгенерировать ключ",
      col_name: "Название ключа",
      col_status: "Статус",
      col_usage: "Использование квоты",
      col_rpm: "Лимит RPM",
      col_actions: "Действия",
      usage_tokens: "токенов",
      tokens_suffix: "токенов",
      aria_save: "Сохранить изменения",
      aria_cancel: "Отменить редактирование",
      aria_edit: "Редактировать лимиты",
      aria_pause: "Приостановить ключ",
      aria_resume: "Возобновить ключ",
      created_title: "API-ключ успешно создан",
      created_desc: "Ключ отображается только один раз — сохраните его сейчас.",
      btn_copy: "Скопировать",
      copied: "Скопировано!",
      btn_done: "Готово",
      confirm_delete: "Вы точно хотите удалить API-ключ",
      placeholder_unlimited: "0 или пусто — без лимита",
      btn_delete: "Удалить ключ"
    },
    credentials: {
      title: "Аккаунты нейросетей",
      desc: "Подключайте API-ключи провайдеров или Google-аккаунт. Нагрузка распределяется автоматически для экономии лимитов и обработки ошибок.",
      btn_add: "Добавить аккаунт",
      btn_cancel: "Отмена",
      form_title: "Подключить аккаунт",
      form_name: "Название аккаунта",
      form_provider: "Провайдер",
      form_type: "Тип аккаунта",
      form_priority: "Приоритет (1 = наивысший)",
      form_weight: "Вес (доля трафика)",
      form_concurrency: "Макс. параллельных запросов",
      form_details: "Настройки API (JSON, необязательно)",
      form_details_placeholder: '{\n  "api_key": "ваш-ключ-api"\n}',
      form_name_placeholder: "например, Мой аккаунт OpenAI",
      form_btn: "Подключить аккаунт",
      option_byo: "Свой API-ключ",
      option_managed: "Google-аккаунт (Gemini)",
      col_id: "Аккаунт",
      col_provider: "Провайдер",
      col_type: "Тип",
      col_priority_weight: "Приоритет и вес",
      col_status: "Статус",
      tag_managed: "Google",
      tag_byo: "Свой ключ",
      tier_weight: "Приоритет {priority} (вес: {weight})",
      lbl_requests: "Всего запросов",
      lbl_latency: "Ср. время ответа",
      lbl_errors: "Ошибки",
      lbl_controls: "Настройки роутинга",
      lbl_priority: "Приоритет",
      lbl_weight: "Вес",
      lbl_concurrency: "Параллельные запросы",
      lbl_manual_state: "Статус (вручную)",
      lbl_json_spec: "КОНФИГУРАЦИЯ",
      btn_save_settings: "Сохранить изменения",
      btn_close: "Закрыть",
      latency_suffix: " мс",
      latency_na: "Н/Д",
      lbl_connection_method: "Способ подключения",
      option_auto_oauth: "Автоматически (нужен проект в GCP)",
      option_manual_sdk: "Вручную через SDK Google (без проекта GCP)",
      manual_sdk_instructions_title: "Как подключить без проекта в GCP:",
      manual_sdk_instruction_1: "Нажмите ссылку ниже — откроется экран согласия Google.",
      manual_sdk_instruction_2: "Войдите в Google-аккаунт и дайте разрешения.",
      manual_sdk_instruction_3: "После перенаправления на localhost (страница не загрузится — это нормально) скопируйте весь URL из адресной строки.",
      manual_sdk_instruction_4: "Вставьте этот URL или код авторизации в поле ниже и нажмите «Подключить».",
      lbl_authorize_link: "Авторизовать Google-аккаунт",
      placeholder_code_or_url: "Вставьте redirect-URL или код авторизации",
      btn_connect_sdk: "Подключить по коду",
      msg_connecting: "Подключение и проверка квот...",
      lbl_advanced: "Дополнительно",
      form_api_key: "API-ключ",
      form_base_url: "Base URL (необязательно)",
      btn_refresh_quotas: "Обновить квоты",
      btn_connect_google: "Подключить Google",
      btn_delete: "Удалить",
      confirm_delete: "Вы точно хотите удалить этот аккаунт?",
      lbl_token_quota: "Квота токенов",
      lbl_reset_window: "Окно сброса (в секундах)",
      lbl_reset_window_short: "Окно сброса (сек.)",
      lbl_supported_models: "Поддерживаемые модели (через запятую)",
      lbl_models_short: "Модели (через запятую)",
      lbl_remaining: "Осталось:",
      lbl_usage_limits: "Лимиты использования Antigravity",
      btn_show_model_quotas: "Показать квоты моделей",
      btn_hide_model_quotas: "Скрыть квоты моделей",
      lbl_no_models: "Модели не настроены"
    },
    logs: {
      title: "История запросов",
      desc: "Все запросы через шлюз в реальном времени.",
      btn_simulate: "Отправить тестовый запрос",
      btn_clear: "Очистить логи",
      col_time: "Время",
      col_key: "API-ключ",
      col_pool: "Использованный аккаунт",
      col_model: "Модель",
      col_latency: "Время ответа",
      col_tokens: "Токены",
      col_cost: "Стоимость",
      col_response: "Результат",
      empty_state: "Запросов пока нет. Нажмите «Отправить тестовый запрос», чтобы попробовать.",
      tokens_format: "{prompt}вх / {completion}исх",
      test_modal_title: "Тестовый запрос",
      lbl_select_model: "Выберите модель",
      lbl_prompt: "Сообщение (промпт)",
      placeholder_prompt: "Введите сообщение для ИИ...",
      btn_send: "Отправить запрос",
      btn_sending: "Отправка...",
      lbl_response: "Ответ модели",
      lbl_tokens: "Потрачено токенов",
      lbl_latency: "Время ответа",
      msg_no_active_creds: "Нужен хотя бы один активный аккаунт для отправки запросов.",
      err_rate_limit: "429 Лимит запросов",
      err_unauthorized: "401 Ошибка авторизации",
      err_unavailable: "503 Сервис недоступен",
      msg_executing: "Запрос отправлен провайдеру ИИ...",
      msg_error: "Произошла ошибка:",
      msg_empty_response: "[Пустой ответ]"
    },
    mock: {
      "Antigravity OpenAI Enterprise": "Antigravity OpenAI Enterprise",
      "BYO Anthropic Production": "BYO Anthropic Production",
      "BYO OpenAI Backup": "BYO OpenAI Backup",
      "BYO Cohere Command": "BYO Cohere Command",
      "BYO OpenAI Legacy": "BYO OpenAI Legacy",
      "Antigravity Gemini Flash": "Antigravity Gemini Flash",
      "sk-lev-prod-core": "sk-lev-prod-core",
      "sk-lev-dev-sandbox": "sk-lev-dev-sandbox",
      "sk-lev-marketing-ai": "sk-lev-marketing-ai",
      "sk-lev-stg-test": "sk-lev-stg-test"
    }
  }
};
