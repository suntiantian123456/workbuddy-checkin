# workbuddy-checkin

WorkBuddy 每日签到云端兜底（GitHub Actions）。
凭据以 Secret `WB_REFRESH_TOKEN` 保存，不入库。

refreshToken 有效期约 30 天；过期后需在本机重新导出并更新 Secret。
