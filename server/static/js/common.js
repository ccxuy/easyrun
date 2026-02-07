/**
 * EZ Common JS - 公共工具函数
 */

// Toast 通知
window.showToast = function(msg, type, duration) {
    type = type || 'info';
    duration = duration || 3000;
    var container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(function() {
        toast.style.animation = 'toast-out 0.3s ease-in forwards';
        setTimeout(function() { toast.remove(); }, 300);
    }, duration);
};

// HTML 转义
window.escapeHtml = function(str) {
    var div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
};

// 状态标签映射
window.statusLabels = {
    success: '成功', failed: '失败', error: '错误',
    running: '运行中', pending: '等待中', cancelled: '已取消',
    timeout: '超时', skipped: '已跳过'
};

// 状态 badge HTML
window.statusBadgeHtml = function(status) {
    var label = statusLabels[status] || status;
    return '<span class="status-badge ' + escapeHtml(status) + '">' + escapeHtml(label) + '</span>';
};

// 格式化耗时 (两个时间戳)
window.formatDuration = function(started, finished) {
    if (!started || !finished) return '-';
    var ms = new Date(finished) - new Date(started);
    return formatDurationMs(ms);
};

// 格式化耗时 (毫秒)
window.formatDurationMs = function(ms) {
    if (ms < 0) return '-';
    var s = Math.round(ms / 1000);
    if (s < 60) return s + '秒';
    if (s < 3600) return Math.floor(s / 60) + '分' + (s % 60) + '秒';
    return Math.floor(s / 3600) + '时' + Math.floor((s % 3600) / 60) + '分';
};

// 格式化耗时 (秒数)
window.formatDurationSec = function(seconds) {
    if (!seconds && seconds !== 0) return '-';
    return formatDurationMs(seconds * 1000);
};

// 相对时间
window.formatTimeAgo = function(isoStr) {
    if (!isoStr) return '-';
    var d = new Date(isoStr);
    var now = new Date();
    var diffSec = Math.floor((now - d) / 1000);
    if (diffSec < 60) return diffSec + '秒前';
    if (diffSec < 3600) return Math.floor(diffSec / 60) + '分钟前';
    if (diffSec < 86400) return Math.floor(diffSec / 3600) + '小时前';
    if (diffSec < 604800) return Math.floor(diffSec / 86400) + '天前';
    return d.toLocaleString('zh-CN');
};

// 执行类型标签
window.execTypeLabels = {
    plan: '计划', task: '任务', cli: 'CLI'
};

// 执行类型 badge
window.execTypeBadgeHtml = function(type) {
    var label = execTypeLabels[type] || type;
    var cls = type === 'plan' ? 'badge-plan' : (type === 'cli' ? 'badge-cli' : 'badge-task');
    return '<span class="badge ' + cls + '">' + escapeHtml(label) + '</span>';
};
