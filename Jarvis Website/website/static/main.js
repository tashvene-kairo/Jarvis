let projects = [];
let meetings = [];
let selectedMeetingKey = null;
let calendarEvents = [];
let projectCalendarEvents = {};
let calendarDate = new Date();
let selectedCalendarDate = new Date();
let editingCalendarEventId = null;
let canViewStakeholders = false;
const documents = [
  ['Foundation Progress Report.pdf', 'PDF · 2.4 MB', 'Data Center Phase 2'],
  ['HVAC Specification Change.docx', 'DOCX · 840 KB', 'Data Center Phase 2'],
  ['Site Coordination Notes.txt', 'TXT · 18 KB', 'Warehouse Construction'],
  ['Executive Summary.xlsx', 'XLSX · 1.1 MB', 'Office Tower Renovation']
];

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const titleCase = value => value.replace(/\b\w/g, letter => letter.toUpperCase());
function clearSearchAutofill() {
  ['#dashboardProjectSearch', '#projectSearch', '#meetingSearch'].forEach(selector => { const input = $(selector); if (input) { input.value = ''; input.readOnly = true; input.addEventListener('focus', () => { input.readOnly = false; }, { once: true }); } });
}
clearSearchAutofill();
window.addEventListener('pageshow', clearSearchAutofill);

document.addEventListener('submit', event => {
  const form = event.target.closest('[data-confirm]');
  if (form && !window.confirm(form.dataset.confirm)) event.preventDefault();
});

function addProjectArchiveLinks() {
  document.querySelectorAll('.project-page-actions').forEach(actions => {
    if (actions.querySelector('.project-archive-link')) return;
    const link = document.createElement('a');
    link.className = 'secondary-button project-archive-link';
    link.href = '/project/archive';
    link.textContent = 'Project archive';
    actions.append(link);
  });
}
addProjectArchiveLinks();
window.addEventListener('pageshow', addProjectArchiveLinks);
$('#projectFilter')?.querySelectorAll('option[value="completed"], option[value="deferred"], option[value="cancelled"]')
  .forEach(option => option.remove());

function renderProjects(list = projects) {
  const recent = $('#recentProjects');
  const grid = $('#projectGrid');
  const dashboardGrid = $('#dashboardProjectGrid');
  if (recent) recent.innerHTML = '';
  const cards = list.map(project => `<article class="project-card"><small class="project-id">${project.display_id}</small><h3>${project.name}</h3><p>${project.company || 'Company not set'}${project.client ? `, ${project.client}` : ''}</p>${(project.tasks || []).map(task => `<a class="project-task-reminder alert-${task.alert_class}" href="/meeting/${task.meeting_id}?task_id=${task.task_id}"><span>${task.title}</span><small>${task.due_date ? `Due ${task.due_date} · ` : ''}<b>${task.alert}</b></small></a>`).join('')}<span class="status-pill ${project.status === 'planning' ? 'green' : 'blue'}">${titleCase(project.status)}</span><a class="project-details-button" href="/?view=projects&project_id=${project.id}">View Details</a></article>`).join('');
  if (grid) grid.innerHTML = cards;
  const dashboardList = list.filter(project => !['completed', 'deferred', 'cancelled'].includes((project.status || '').toLowerCase()));
  if (dashboardGrid) dashboardGrid.innerHTML = dashboardList.map(project => `<article class="project-card" data-dashboard-project-id="${project.id}"><small class="project-id">${escapeHtml(project.display_id)}</small><h3>${escapeHtml(project.name)}</h3><p>${escapeHtml(project.company || 'Company not set')}${project.client ? `, ${escapeHtml(project.client)}` : ''}</p>${(project.tasks || []).map(task => `<a class="project-task-reminder alert-${escapeHtml(task.alert_class)}" href="/meeting/${task.meeting_id}?task_id=${task.task_id}"><span>${escapeHtml(task.title)}</span><small>${task.due_date ? `Due ${escapeHtml(task.due_date)} · ` : ''}<b>${escapeHtml(task.alert)}</b></small></a>`).join('')}<div class="project-dashboard-calendar-alerts" data-dashboard-calendar-alerts="${project.id}">${dashboardCalendarAlertsMarkup(project)}</div><span class="status-pill ${project.status === 'planning' ? 'green' : 'blue'}">${titleCase(project.status)}</span><a class="project-details-button" href="/?view=projects&project_id=${project.id}">View Details</a></article>`).join('');
  renderProjectDirectory(list);
  const meetingProject = $('#meetingProject');
  if (meetingProject) meetingProject.innerHTML = list.map(project => `<option value="${project.id}">${project.name}</option>`).join('');
}

function dashboardCalendarAlertsMarkup(project) {
  return (project.calendar_events || []).map(event => `<a class="project-calendar-reminder" href="/?view=projects&project_id=${encodeURIComponent(project.id)}&calendar_event_id=${encodeURIComponent(event.id)}"><small class="calendar-reminder-label">Calendar</small><span>${escapeHtml(event.title)}</span><small>${escapeHtml(event.date)}${event.start_time ? ` · ${escapeHtml(event.start_time)}` : ''}</small></a>`).join('');
}

function updateDashboardProjectEvent(projectId, eventId, savedEvent = null) {
  const project = projects.find(item => String(item.id) === String(projectId));
  if (!project) return;
  const eventNumericId = Number(String(eventId).replace(/^event-/, ''));
  const existingEvents = project.calendar_events || [];
  project.calendar_events = existingEvents.filter(item => Number(item.id) !== eventNumericId);
  if (savedEvent) {
    const now = new Date();
    const today = calendarDateKey(now);
    const eventTime = savedEvent.end_time || savedEvent.start_time;
    const isUpcoming = savedEvent.date > today
      || (savedEvent.date === today && (!eventTime || eventTime > `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`));
    if (isUpcoming) {
      project.calendar_events.push({
        id: eventNumericId,
        title: savedEvent.title,
        date: savedEvent.date,
        start_time: savedEvent.start_time || '',
        end_time: savedEvent.end_time || '',
      });
      project.calendar_events.sort((left, right) => left.date.localeCompare(right.date) || (left.start_time || '').localeCompare(right.start_time || ''));
    }
  }
  const alertContainer = document.querySelector(`[data-dashboard-calendar-alerts="${projectId}"]`);
  if (alertContainer) alertContainer.innerHTML = dashboardCalendarAlertsMarkup(project);
}

function renderProjectDirectory(list = projects) {
  const target = $('#projectDirectory');
  if (!target) return;
  target.innerHTML = list.map(project => {
    const meetings = project.meetings || [];
    const detailRows = [
      ['Project ID', project.display_id],
      ['Project name', project.name],
      ['Project Site / Location', project.project_site],
      ['Status', titleCase(project.status || 'Planning')],
      ['Company', project.company],
      ['Client', project.client],
      ['Sub Contractor / Vendor', project.contractor],
      ['Consultant', project.consultant],
      ['Description', project.description],
      ['Purchase order date', project.purchase_order_date],
      ['Issued date', project.issued_date],
    ].map(([label, value]) => `<tr><th scope="row">${escapeHtml(label)}</th><td>${escapeHtml(value || 'Not set')}</td></tr>`).join('');
    const meetingRows = meetings.map(meeting => {
      const meetingDetails = [
        ['Type', meeting.type],
        ['Location', meeting.location],
        ['Description', meeting.description],
        ['Agenda', meeting.agenda],
        ['Start / End', [meeting.start_time, meeting.end_time].filter(Boolean).join(' - ')],
        ['Chairperson', meeting.chairperson],
      ].map(([label, value]) => `<tr><th scope="row">${escapeHtml(label)}</th><td>${escapeHtml(value || 'Not set')}</td></tr>`).join('');
      return `<details class="project-directory-meeting"><summary class="project-directory-meeting-head"><strong>${escapeHtml(meeting.meeting_id)} · ${escapeHtml(meeting.title)}</strong><span>${escapeHtml(meeting.revision)} · ${escapeHtml(meeting.date)}</span><span class="details-toggle" aria-hidden="true"></span></summary><div class="project-directory-details"><table class="project-preview-table meeting-preview-table"><tbody>${meetingDetails}</tbody></table><div class="project-directory-actions"><a class="secondary-button" href="/meeting/${meeting.id}">View meeting</a></div></div>${meeting.tasks?.length ? `<div class="project-directory-tasks">${meeting.tasks.map(task => `<a href="/meeting/${meeting.id}?task_id=${task.id}"><strong>${escapeHtml(task.title)}</strong><small>${escapeHtml(task.status)}${task.due_date ? ` · Due ${escapeHtml(task.due_date)}` : ''}${task.assigned_to ? ` · ${escapeHtml(task.assigned_to)}` : ''}</small></a>`).join('')}</div>` : '<small class="project-detail-intro">No open action items.</small>'}</details>`;
    }).join('');
    const status = (project.status || 'planning').toLowerCase();
    return `<article class="project-directory-card"><div class="project-directory-head"><div><small class="project-id">${escapeHtml(project.display_id)}</small><h3>${escapeHtml(project.name)}</h3><p>${escapeHtml(project.company || 'Company not set')}${project.client ? `, ${escapeHtml(project.client)}` : ''}</p></div><span class="status-pill ${status === 'planning' ? 'green' : 'blue'}">${escapeHtml(titleCase(status))}</span></div><div class="project-directory-actions"><button class="secondary-button project-details-toggle" type="button" aria-expanded="false" aria-controls="project-details-${project.id}">Show details</button><button class="secondary-button project-calendar-toggle" type="button" aria-expanded="false" aria-controls="project-calendar-${project.id}" data-project-id="${project.id}">Calendar</button><form method="post" action="/project/${project.id}/archive" data-confirm="Move ${escapeHtml(project.name)} to Project archive? You can restore within 30 days."><button class="project-trash-button" type="submit" aria-label="Move ${escapeHtml(project.name)} to Project archive" title="Move to Project archive"><i class="fa fa-trash" aria-hidden="true"></i></button></form></div><div class="project-details-panel" id="project-details-${project.id}" hidden><table class="project-preview-table"><tbody>${detailRows}</tbody></table><div class="project-details-footer"><a class="secondary-button" href="/project/${encodeURIComponent(project.name)}">Edit project</a></div><details class="project-directory-meetings"><summary class="project-directory-meetings-toggle"><strong>Meetings (${meetings.length})</strong><span class="meetings-toggle-label" aria-hidden="true"></span></summary>${meetingRows || '<p class="project-detail-intro">No meetings for this project.</p>'}</details></div><section class="project-calendar-panel" id="project-calendar-${project.id}" data-project-calendar="${project.id}" data-project-name="${escapeHtml(project.name)}" hidden></section></article>`;
  }).join('') || '<p class="project-detail-intro">No projects found.</p>';
  target.querySelectorAll('.project-directory-card').forEach(card => {
    const panel = card.querySelector('.project-details-panel');
    card.querySelectorAll('.project-details-toggle').forEach(button => button.addEventListener('click', () => {
      panel.hidden = !panel.hidden;
      card.querySelectorAll('.project-details-toggle').forEach(toggle => {
        toggle.setAttribute('aria-expanded', String(!panel.hidden));
        if (toggle.closest('.project-directory-actions')) toggle.textContent = panel.hidden ? 'Show details' : 'Hide details';
      });
    }));
    card.querySelector('.project-calendar-toggle')?.addEventListener('click', event => {
      const button = event.currentTarget;
      const calendarPanel = card.querySelector('.project-calendar-panel');
      calendarPanel.hidden = !calendarPanel.hidden;
      button.setAttribute('aria-expanded', String(!calendarPanel.hidden));
      button.textContent = calendarPanel.hidden ? 'Calendar' : 'Hide calendar';
      if (!calendarPanel.hidden && !calendarPanel.dataset.loaded) loadProjectCalendar(calendarPanel);
    });
  });
  target.querySelectorAll('[data-project-calendar]').forEach(bindProjectCalendar);
}
function renderMeetings(list = meetings) {
  const target = $('#upcomingMeetings');
  const directory = $('#meetingDirectory');
  const dashboardMarkup = meetings.map(meeting => {
    const tag = meeting.is_current ? 'a' : 'div';
    const href = meeting.is_current ? ` href="/meeting/${meeting.id}"` : '';
    const modifiedDate = meeting.modified ? new Date(meeting.modified).toLocaleDateString() : 'Unknown';
    return `<${tag} class="meeting-row"${href}><span class="meeting-icon"></span><span class="row-copy"><strong>${meeting.project_id} ${meeting.title} - MOM${String(meeting.id).padStart(4, '0')}</strong><small>Meeting date: ${meeting.date || 'Not set'}<br>Modified: ${modifiedDate}<br>${meeting.project}${meeting.company || meeting.client ? ` · ${meeting.company || ''}${meeting.client ? `, ${meeting.client}` : ''}` : ''}</small></span><span class="status-pill blue">${meeting.revision}</span></${tag}>`;
  }).join('');
  if (target) target.innerHTML = dashboardMarkup;
  if (!directory) return;
  if (!list.some(meeting => `${meeting.id}:${meeting.revision_number}` === selectedMeetingKey)) {
    selectedMeetingKey = list.length ? `${list[0].id}:${list[0].revision_number}` : null;
  }
  directory.innerHTML = list.length ? list.map(meeting => {
    const modifiedDate = meeting.modified ? new Date(meeting.modified).toLocaleDateString() : 'Unknown';
    const key = `${meeting.id}:${meeting.revision_number}`;
    const isSelected = key === selectedMeetingKey;
    return `<article class="meeting-directory-card${isSelected ? ' is-selected' : ''}">
      <button class="meeting-directory-select" type="button" data-meeting-key="${escapeHtml(key)}" aria-pressed="${isSelected}">
        <span class="meeting-icon"></span>
        <span class="row-copy"><strong>${escapeHtml(meeting.project_id)} ${escapeHtml(meeting.title)} - MOM${String(meeting.id).padStart(4, '0')}</strong><small>Meeting date: ${escapeHtml(meeting.date || 'Not set')}<br>Modified: ${escapeHtml(modifiedDate)}<br>${escapeHtml(meeting.project)}${meeting.company || meeting.client ? ` · ${escapeHtml(meeting.company || '')}${meeting.client ? `, ${escapeHtml(meeting.client)}` : ''}` : ''}</small></span>
        <span class="status-pill blue">${escapeHtml(meeting.revision)}</span>
      </button>
      <form class="meeting-archive-form" method="post" action="/meeting/${meeting.id}/revision/${encodeURIComponent(meeting.revision_order)}/archive" data-confirm="Move Rev_${escapeHtml(meeting.revision_number)} of ${escapeHtml(meeting.title)} to Recently deleted?">
        <button class="meeting-trash-button" type="submit" aria-label="Archive ${escapeHtml(meeting.title)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg></button>
      </form>
    </article>`;
  }).join('') : '<p class="meeting-list-empty">No meetings match your search.</p>';
  directory.querySelectorAll('.meeting-directory-select').forEach(button => button.addEventListener('click', () => {
    selectedMeetingKey = button.dataset.meetingKey;
    const selectedMeeting = list.find(meeting => `${meeting.id}:${meeting.revision_number}` === selectedMeetingKey);
    if (!selectedMeeting) return;
    directory.querySelectorAll('.meeting-directory-card').forEach(row => {
      const selected = row.contains(button);
      row.classList.toggle('is-selected', selected);
      row.querySelector('.meeting-directory-select')?.setAttribute('aria-pressed', String(selected));
    });
    renderMeetingPreview(selectedMeeting);
  }));
  const selectedMeeting = list.find(meeting => `${meeting.id}:${meeting.revision_number}` === selectedMeetingKey);
  renderMeetingPreview(selectedMeeting);
}

function renderMeetingPreview(meeting) {
  const title = $('#meetingPreviewTitle');
  const metadata = $('#meetingPreviewMetadata');
  const editLink = $('#meetingPreviewEdit');
  const frame = $('#meetingPreviewFrame');
  const empty = $('#meetingPreviewEmpty');
  if (!title || !metadata || !editLink || !frame || !empty) return;
  if (!meeting) {
    title.textContent = 'Select a meeting';
    metadata.textContent = 'Choose a meeting revision from the list to preview its minutes.';
    editLink.hidden = true;
    frame.hidden = true;
    frame.removeAttribute('src');
    empty.hidden = false;
    return;
  }
  title.textContent = `${meeting.project_id} ${meeting.title} - MOM${String(meeting.id).padStart(4, '0')} · ${meeting.revision}`;
  metadata.textContent = `Meeting date: ${meeting.date || 'Not set'} · Modified: ${meeting.modified ? new Date(meeting.modified).toLocaleDateString() : 'Unknown'}`;
  editLink.href = `/meeting/${meeting.id}/edit`;
  editLink.textContent = meeting.is_current ? 'Edit meeting' : 'Edit latest meeting';
  editLink.hidden = false;
  empty.hidden = true;
  frame.hidden = false;
  frame.title = `${meeting.title} ${meeting.revision} PDF preview`;
  const previewUrl = `/meeting/${meeting.id}/export/pdf?inline=1&revision_order=${encodeURIComponent(meeting.revision_order)}`;
  if (frame.getAttribute('src') !== previewUrl) frame.src = previewUrl;
}

function calendarDateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function renderCalendarEvents() {
  const target = $('#calendarEvents');
  if (!target) return;
  const selectedKey = calendarDateKey(selectedCalendarDate);
  const events = calendarEvents.filter(event => event.date === selectedKey);
  target.innerHTML = events.length ? events.map(event => event.source === 'meeting' ? `<a class="calendar-event" href="/meeting/${event.id.replace('meeting-', '')}"><strong>${escapeHtml(event.title)}</strong><small>${escapeHtml(event.project)}${event.start_time ? ` · ${escapeHtml(event.start_time)}${event.end_time ? ` - ${escapeHtml(event.end_time)}` : ''}` : ''}</small></a>` : `<div class="calendar-event"><strong>${escapeHtml(event.title)}</strong><small>${escapeHtml(event.project)}${event.start_time ? ` · ${escapeHtml(event.start_time)}${event.end_time ? ` - ${escapeHtml(event.end_time)}` : ''}` : ''}</small>${event.event_description ? `<p>${escapeHtml(event.event_description)}</p>` : ''}<button class="text-button calendar-edit-button" type="button" data-calendar-edit="${escapeHtml(event.id)}">Edit</button></div>`).join('') : '<p class="calendar-empty">No meetings on this date.</p>';
  target.querySelectorAll('[data-calendar-edit]').forEach(button => button.addEventListener('click', () => beginCalendarEdit(button.dataset.calendarEdit)));
}

function renderCalendar() {
  const monthLabel = $('#calendarMonth');
  const grid = $('#calendarGrid');
  if (!monthLabel || !grid) return;
  monthLabel.textContent = calendarDate.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
  const firstDay = new Date(calendarDate.getFullYear(), calendarDate.getMonth(), 1).getDay();
  const daysInMonth = new Date(calendarDate.getFullYear(), calendarDate.getMonth() + 1, 0).getDate();
  const todayKey = calendarDateKey(new Date());
  const selectedKey = calendarDateKey(selectedCalendarDate);
  const cells = [];
  for (let index = 0; index < firstDay; index += 1) cells.push('<span class="calendar-day is-empty"></span>');
  for (let day = 1; day <= daysInMonth; day += 1) {
    const key = calendarDateKey(new Date(calendarDate.getFullYear(), calendarDate.getMonth(), day));
    const hasEvent = calendarEvents.some(event => event.date === key);
    cells.push(`<button class="calendar-day${key === todayKey ? ' is-today' : ''}${key === selectedKey ? ' is-selected' : ''}${hasEvent ? ' has-event' : ''}" type="button" data-calendar-date="${key}">${day}</button>`);
  }
  grid.innerHTML = cells.join('');
  grid.querySelectorAll('[data-calendar-date]').forEach(button => button.addEventListener('click', () => {
    const [year, month, day] = button.dataset.calendarDate.split('-').map(Number);
    selectedCalendarDate = new Date(year, month - 1, day);
    $('#calendarDate').value = button.dataset.calendarDate;
    renderCalendar();
  }));
  renderCalendarEvents();
}

function projectCalendarMarkup() {
  return `<div class="project-calendar-heading"><h4>Project calendar</h4><button class="text-button" type="button" data-project-calendar-close>Close</button></div><div class="calendar-heading"><button class="icon-button" type="button" data-project-calendar-previous aria-label="Previous month">‹</button><h3 data-project-calendar-month></h3><button class="icon-button" type="button" data-project-calendar-next aria-label="Next month">›</button></div><div class="calendar-weekdays"><span>Sun</span><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span><span>Sat</span></div><div class="calendar-grid" data-project-calendar-grid></div><div class="calendar-events" data-project-calendar-events></div><form class="calendar-form" data-project-calendar-form><h4>Schedule an event</h4><label>Event title<input type="text" data-project-calendar-title required placeholder="Event title"></label><label>Event description<textarea rows="3" data-project-calendar-description placeholder="Describe the event"></textarea></label><div class="calendar-form-grid"><label>Date<input type="date" data-project-calendar-date-input required></label><label>Start<input type="time" data-project-calendar-start></label><label>End<input type="time" data-project-calendar-end></label></div><div class="calendar-form-actions"><button class="primary-button" type="submit" data-project-calendar-submit>Add to calendar</button><button class="secondary-button" type="button" data-project-calendar-cancel hidden>Cancel</button><button class="danger-button" type="button" data-project-calendar-delete hidden>Delete</button></div></form>`;
}

async function loadProjectCalendar(panel, targetEventId = '') {
  panel.innerHTML = projectCalendarMarkup();
  if (!panel.dataset.selectedDate) panel.dataset.selectedDate = calendarDateKey(new Date());
  if (!panel.dataset.month) panel.dataset.month = `${panel.dataset.selectedDate.slice(0, 7)}-01`;
  bindProjectCalendar(panel);
  try {
    const response = await fetch(`/api/calendar-events?project_id=${encodeURIComponent(panel.dataset.projectCalendar)}`);
    if (!response.ok) throw new Error('Unable to load this project calendar.');
    const data = await response.json();
    projectCalendarEvents[panel.dataset.projectCalendar] = data.events || [];
    panel.dataset.loaded = 'true';
    if (targetEventId) {
      const targetEvent = projectCalendarEvents[panel.dataset.projectCalendar].find(item => item.id === `event-${targetEventId}`);
      if (!targetEvent) {
        toast('That event is no longer available in this project calendar.');
        return;
      }
      panel.dataset.selectedDate = targetEvent.date;
      panel.dataset.month = `${targetEvent.date.slice(0, 7)}-01`;
    }
    renderProjectCalendar(panel);
    if (targetEventId) {
      const targetRow = [...panel.querySelectorAll('[data-project-calendar-event-id]')]
        .find(row => row.dataset.projectCalendarEventId === `event-${targetEventId}`);
      targetRow?.classList.add('is-target-event');
      targetRow?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  } catch (error) {
    panel.querySelector('[data-project-calendar-events]').innerHTML = `<p class="calendar-empty">${escapeHtml(error.message)}</p>`;
    toast(error.message);
  }
}

function renderProjectCalendar(panel) {
  const projectId = panel.dataset.projectCalendar;
  const [year, month] = panel.dataset.month.split('-').map(Number);
  const selectedDate = panel.dataset.selectedDate;
  const date = new Date(year, month - 1, 1);
  const monthHeading = panel.querySelector('[data-project-calendar-month]');
  const grid = panel.querySelector('[data-project-calendar-grid]');
  const eventsTarget = panel.querySelector('[data-project-calendar-events]');
  if (!monthHeading || !grid || !eventsTarget) return;
  monthHeading.textContent = date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
  const firstDay = date.getDay();
  const daysInMonth = new Date(year, month, 0).getDate();
  const todayKey = calendarDateKey(new Date());
  const cells = [];
  for (let index = 0; index < firstDay; index += 1) cells.push('<span class="calendar-day is-empty"></span>');
  for (let day = 1; day <= daysInMonth; day += 1) {
    const key = calendarDateKey(new Date(year, month - 1, day));
    const hasEvent = (projectCalendarEvents[projectId] || []).some(item => item.date === key);
    cells.push(`<button class="calendar-day${key === todayKey ? ' is-today' : ''}${key === selectedDate ? ' is-selected' : ''}${hasEvent ? ' has-event' : ''}" type="button" data-project-calendar-day="${key}">${day}</button>`);
  }
  grid.innerHTML = cells.join('');
  panel.querySelector('[data-project-calendar-date-input]').value = selectedDate;
  const selectedEvents = (projectCalendarEvents[projectId] || []).filter(item => item.date === selectedDate);
  eventsTarget.innerHTML = selectedEvents.length
    ? selectedEvents.map(item => item.source === 'meeting'
      ? `<a class="calendar-event" data-project-calendar-event-id="${escapeHtml(item.id)}" href="/meeting/${encodeURIComponent(item.id.replace('meeting-', ''))}"><strong>${escapeHtml(item.title)}</strong><small>${item.start_time ? `${escapeHtml(item.start_time)}${item.end_time ? ` - ${escapeHtml(item.end_time)}` : ''}` : 'Meeting'}</small></a>`
      : `<div class="calendar-event" data-project-calendar-event-id="${escapeHtml(item.id)}"><strong>${escapeHtml(item.title)}</strong><small>${item.start_time ? `${escapeHtml(item.start_time)}${item.end_time ? ` - ${escapeHtml(item.end_time)}` : ''}` : 'Event'}</small>${item.event_description ? `<p>${escapeHtml(item.event_description)}</p>` : ''}<button class="text-button calendar-edit-button" type="button" data-project-calendar-edit="${escapeHtml(item.id)}">Edit</button></div>`).join('')
    : '<p class="calendar-empty">No meetings or events on this date.</p>';
}

function resetProjectCalendarForm(panel) {
  panel.dataset.editingEventId = '';
  panel.querySelector('[data-project-calendar-form]').reset();
  panel.querySelector('[data-project-calendar-date-input]').value = panel.dataset.selectedDate;
  panel.querySelector('[data-project-calendar-submit]').textContent = 'Add to calendar';
  panel.querySelector('[data-project-calendar-cancel]').hidden = true;
  panel.querySelector('[data-project-calendar-delete]').hidden = true;
}

function bindProjectCalendar(panel) {
  if (panel.dataset.bound === 'true') return;
  panel.dataset.bound = 'true';
  panel.addEventListener('click', async event => {
    const close = event.target.closest('[data-project-calendar-close]');
    if (close) {
      const toggle = document.querySelector(`.project-calendar-toggle[data-project-id="${panel.dataset.projectCalendar}"]`);
      panel.hidden = true;
      if (toggle) {
        toggle.textContent = 'Calendar';
        toggle.setAttribute('aria-expanded', 'false');
      }
      return;
    }
    if (event.target.closest('[data-project-calendar-previous]')) {
      const [year, month] = panel.dataset.month.split('-').map(Number);
      panel.dataset.month = calendarDateKey(new Date(year, month - 2, 1));
      panel.dataset.month = `${panel.dataset.month.slice(0, 7)}-01`;
      renderProjectCalendar(panel);
    } else if (event.target.closest('[data-project-calendar-next]')) {
      const [year, month] = panel.dataset.month.split('-').map(Number);
      panel.dataset.month = calendarDateKey(new Date(year, month, 1));
      panel.dataset.month = `${panel.dataset.month.slice(0, 7)}-01`;
      renderProjectCalendar(panel);
    } else {
      const dayButton = event.target.closest('[data-project-calendar-day]');
      if (dayButton) {
        panel.dataset.selectedDate = dayButton.dataset.projectCalendarDay;
        resetProjectCalendarForm(panel);
        renderProjectCalendar(panel);
      }
    }
    const editButton = event.target.closest('[data-project-calendar-edit]');
    if (editButton) {
      const item = (projectCalendarEvents[panel.dataset.projectCalendar] || []).find(calendarItem => calendarItem.id === editButton.dataset.projectCalendarEdit);
      if (!item || item.source !== 'event') return;
      panel.dataset.editingEventId = item.id;
      panel.querySelector('[data-project-calendar-title]').value = item.title;
      panel.querySelector('[data-project-calendar-description]').value = item.event_description || '';
      panel.querySelector('[data-project-calendar-date-input]').value = item.date;
      panel.querySelector('[data-project-calendar-start]').value = item.start_time || '';
      panel.querySelector('[data-project-calendar-end]').value = item.end_time || '';
      panel.querySelector('[data-project-calendar-submit]').textContent = 'Save changes';
      panel.querySelector('[data-project-calendar-cancel]').hidden = false;
      panel.querySelector('[data-project-calendar-delete]').hidden = false;
    }
    const cancelButton = event.target.closest('[data-project-calendar-cancel]');
    if (cancelButton) resetProjectCalendarForm(panel);
    const deleteButton = event.target.closest('[data-project-calendar-delete]');
    if (deleteButton && panel.dataset.editingEventId && window.confirm('Delete this calendar event?')) {
      const eventId = panel.dataset.editingEventId;
      const response = await fetch(`/api/calendar-events/${encodeURIComponent(eventId.replace('event-', ''))}`, { method: 'DELETE' });
      if (!response.ok) { toast('Unable to delete calendar event.'); return; }
      projectCalendarEvents[panel.dataset.projectCalendar] = projectCalendarEvents[panel.dataset.projectCalendar].filter(item => item.id !== eventId);
      calendarEvents = calendarEvents.filter(item => item.id !== eventId);
      updateDashboardProjectEvent(panel.dataset.projectCalendar, eventId);
      resetProjectCalendarForm(panel);
      renderProjectCalendar(panel);
      renderCalendar();
      toast('Calendar event deleted.');
    }
  });
  panel.addEventListener('submit', async event => {
    const form = event.target.closest('[data-project-calendar-form]');
    if (!form) return;
    event.preventDefault();
    const isEditing = Boolean(panel.dataset.editingEventId);
    const eventId = panel.dataset.editingEventId;
    const response = await fetch(isEditing ? `/api/calendar-events/${encodeURIComponent(eventId.replace('event-', ''))}` : '/api/calendar-events', {
      method: isEditing ? 'PUT' : 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        title: panel.querySelector('[data-project-calendar-title]').value,
        event_description: panel.querySelector('[data-project-calendar-description]').value,
        project_id: panel.dataset.projectCalendar,
        date: panel.querySelector('[data-project-calendar-date-input]').value,
        start_time: panel.querySelector('[data-project-calendar-start]').value,
        end_time: panel.querySelector('[data-project-calendar-end]').value,
      }),
    });
    if (!response.ok) { toast(isEditing ? 'Unable to update calendar event.' : 'Unable to add calendar event.'); return; }
    const savedEvent = await response.json();
    const projectEvents = projectCalendarEvents[panel.dataset.projectCalendar] || [];
    projectCalendarEvents[panel.dataset.projectCalendar] = isEditing
      ? projectEvents.map(item => item.id === savedEvent.id ? savedEvent : item)
      : [...projectEvents, savedEvent];
    updateDashboardProjectEvent(panel.dataset.projectCalendar, savedEvent.id, savedEvent);
    calendarEvents = isEditing
      ? calendarEvents.map(item => item.id === savedEvent.id ? savedEvent : item)
      : [...calendarEvents, savedEvent];
    panel.dataset.selectedDate = savedEvent.date;
    panel.dataset.month = `${savedEvent.date.slice(0, 7)}-01`;
    resetProjectCalendarForm(panel);
    renderProjectCalendar(panel);
    renderCalendar();
    toast(isEditing ? 'Calendar event updated.' : 'Calendar event added.');
  });
}

async function loadCalendar() {
  const response = await fetch('/api/calendar-events');
  if (!response.ok) return;
  const data = await response.json();
  calendarEvents = data.events || [];
  const projectSelect = $('#calendarProject');
  if (projectSelect) projectSelect.innerHTML = (data.projects || []).map(project => `<option value="${project.id}">${project.name}</option>`).join('');
  const requestedDate = new URLSearchParams(window.location.search).get('calendar_date');
  if (requestedDate && /^\d{4}-\d{2}-\d{2}$/.test(requestedDate)) {
    const [year, month, day] = requestedDate.split('-').map(Number);
    selectedCalendarDate = new Date(year, month - 1, day);
    calendarDate = new Date(year, month - 1, 1);
  }
  $('#calendarDate').value = calendarDateKey(selectedCalendarDate);
  renderCalendar();
}

function memberMarkup(member, admin, currentUserId) {
  const inactive = !member.is_active;
  const isCurrentUser = member.id === currentUserId;
  const role = (member.role || '').toLowerCase() === 'admin' ? 'Admin' : 'Member';
  const roleControl = isCurrentUser
    ? `<span class="member-role-static" aria-label="Your role">${role}</span>`
    : `<select class="member-role-select" data-member-role="${member.id}" data-saved-role="${role}" aria-label="Role for ${escapeHtml(member.first_name)} ${escapeHtml(member.last_name)}"><option value="Member" ${role === 'Member' ? 'selected' : ''}>Member</option><option value="Admin" ${role === 'Admin' ? 'selected' : ''}>Admin</option></select><button class="text-button member-role-save" data-member-role-save="${member.id}" type="button" hidden>Save role</button>`;
  return `<div class="member-row${inactive ? ' is-inactive' : ''}${admin && !inactive && !isCurrentUser ? ' has-deactivate' : ''}"><div class="member-summary"><strong>${escapeHtml(member.first_name)}</strong><small>${escapeHtml(member.email)}</small></div>${admin && !inactive ? `<div class="member-controls">${roleControl}${isCurrentUser ? '' : `<button class="secondary-button member-change-password" data-member-change-password="${member.id}" type="button">Change password</button><button class="text-button member-deactivate" data-member-deactivate="${member.id}" type="button">Deactivate</button><div class="member-password-editor" data-member-password-editor="${member.id}" hidden><input class="member-reset-password" data-member-password="${member.id}" type="password" minlength="7" placeholder=""><button class="text-button member-save" data-member-save="${member.id}" type="button" hidden>Save password</button><button class="text-button member-password-cancel" data-member-password-cancel="${member.id}" type="button">Cancel</button></div>`}</div>` : `<span class="member-role-static${inactive ? ' is-inactive' : ''}">${inactive ? 'Deactivated' : role}</span>`}</div>`;
}

const addMemberRoleInput = $('#memberForm [name="role"]');
if (addMemberRoleInput) {
  const roleSelect = document.createElement('select');
  roleSelect.name = 'role';
  roleSelect.required = true;
  roleSelect.innerHTML = '<option value="Member" selected>Member</option><option value="Admin">Admin</option>';
  addMemberRoleInput.replaceWith(roleSelect);
}

function renderOrganisation(data) {
  canViewStakeholders = Boolean(data.is_admin);
  const companyForm = $('#companyForm');
  if (companyForm && !companyForm.elements.company_tax_no) {
    const registrationInput = companyForm.elements.company_reg_no;
    const taxLabel = document.createElement('label');
    taxLabel.textContent = 'Company Tax Number';
    const taxInput = document.createElement('input');
    taxInput.name = 'company_tax_no';
    taxInput.type = 'text';
    taxInput.maxLength = 100;
    taxLabel.append(taxInput);
    registrationInput?.parentElement.after(taxLabel);
  }
  companyForm?.classList.toggle('is-readonly', !data.is_admin);
  const descriptionLabel = companyForm?.querySelector('textarea[name="description"]')?.parentElement;
  if (descriptionLabel?.firstChild) descriptionLabel.firstChild.textContent = 'Other Details';
  if (companyForm) Object.entries(data.company).forEach(([name, value]) => { if (companyForm.elements[name]) companyForm.elements[name].value = value; });
  const companyEmailInput = companyForm?.elements.company_email;
  if (companyEmailInput) {
    companyEmailInput.parentElement.firstChild.textContent = 'Company email';
    companyEmailInput.value = data.company.company_email || '';
  }
  const lastEdited = $('#companyLastEdited');
  if (lastEdited) lastEdited.textContent = data.company.date_issued ? `Last edited: ${data.company.date_issued}` : '';
  const companyPasswordEditor = $('.company-password-editor');
  const changeCompanyPassword = $('#changeCompanyPassword');
  let saveCompanyPassword = $('#saveCompanyPassword');
  let cancelCompanyPassword = $('#cancelCompanyPassword');
  if (companyPasswordEditor && !cancelCompanyPassword) {
    cancelCompanyPassword = document.createElement('button');
    cancelCompanyPassword.className = 'secondary-button admin-only';
    cancelCompanyPassword.id = 'cancelCompanyPassword';
    cancelCompanyPassword.type = 'button';
    cancelCompanyPassword.hidden = true;
    cancelCompanyPassword.textContent = 'Cancel';
    companyPasswordEditor.insertAdjacentElement('afterend', cancelCompanyPassword);
    cancelCompanyPassword.addEventListener('click', () => {
      companyPasswordEditor.hidden = true;
      companyPasswordEditor.querySelector('input').value = '';
      cancelCompanyPassword.hidden = true;
      if (saveCompanyPassword) saveCompanyPassword.hidden = true;
      if (changeCompanyPassword) changeCompanyPassword.hidden = false;
    });
  }
  if (companyPasswordEditor && !saveCompanyPassword) {
    saveCompanyPassword = document.createElement('button');
    saveCompanyPassword.id = 'saveCompanyPassword';
    saveCompanyPassword.type = 'button';
    saveCompanyPassword.className = 'primary-button admin-only';
    saveCompanyPassword.textContent = 'Save company password';
    saveCompanyPassword.hidden = true;
    cancelCompanyPassword?.before(saveCompanyPassword);
    saveCompanyPassword.addEventListener('click', async () => {
      const passwordInput = companyPasswordEditor.querySelector('input');
      if (!passwordInput.value) { toast('Enter a new company password first.'); return; }
      const response = await fetch('/api/organisation/company-password', { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ company_password: passwordInput.value }) });
      const result = await response.json();
      if (!response.ok) { toast(result.error || 'Unable to change company password.'); return; }
      passwordInput.value = '';
      companyPasswordEditor.hidden = true;
      saveCompanyPassword.hidden = true;
      if (cancelCompanyPassword) cancelCompanyPassword.hidden = true;
      if (changeCompanyPassword) changeCompanyPassword.hidden = false;
      await loadOrganisation();
      toast('Company password changed.');
    });
  }
  const adminControls = $$('.admin-only:not(.company-password-editor):not(#cancelCompanyPassword):not(#saveCompanyPassword)');
  adminControls.forEach(control => { control.hidden = !data.is_admin; });
  const activeTarget = $('#activeMembers');
  const inactiveTarget = $('#inactiveMembers');
  if (activeTarget) activeTarget.innerHTML = data.members.filter(member => member.is_active).sort((first, second) => Number(second.id === data.current_user.id) - Number(first.id === data.current_user.id)).map(member => memberMarkup(member, data.is_admin, data.current_user.id)).join('') || '<p class="member-empty">No active team members.</p>';
  if (inactiveTarget) inactiveTarget.innerHTML = data.members.filter(member => !member.is_active).map(member => memberMarkup(member, false, data.current_user.id)).join('') || '<p class="member-empty">No past members.</p>';
  const pastMembersHeading = $('.past-members-heading');
  if (inactiveTarget && pastMembersHeading) {
    let pastMembersToggle = $('#pastMembersToggle');
    if (!pastMembersToggle) {
      pastMembersToggle = document.createElement('button');
      pastMembersToggle.id = 'pastMembersToggle';
      pastMembersToggle.type = 'button';
      pastMembersToggle.className = 'secondary-button admin-only past-members-toggle';
      pastMembersHeading.before(pastMembersToggle);
      pastMembersToggle.addEventListener('click', () => {
        const open = inactiveTarget.hidden;
        inactiveTarget.hidden = !open;
        pastMembersHeading.hidden = !open;
        pastMembersToggle.textContent = open ? 'Hide past members' : 'View past members';
        pastMembersToggle.setAttribute('aria-expanded', String(open));
      });
    }
    pastMembersToggle.hidden = !data.is_admin;
    pastMembersToggle.textContent = 'View past members';
    pastMembersToggle.setAttribute('aria-expanded', 'false');
    pastMembersHeading.hidden = true;
    inactiveTarget.hidden = true;
  }
  ensureStakeholdersView();
  const stakeholdersLink = $('#stakeholdersLink');
  const stakeholdersView = $('#stakeholdersView');
  if (stakeholdersLink) stakeholdersLink.hidden = !canViewStakeholders;
  if (stakeholdersView) stakeholdersView.hidden = !canViewStakeholders;
  if (companyForm) {
    const editableFields = [...companyForm.querySelectorAll('input, textarea')].filter(input => input.name !== 'company_password');
    editableFields.forEach(input => { input.disabled = true; });
    const companySave = companyForm.querySelector('button[type="submit"]');
    if (companySave) { companySave.hidden = true; companySave.classList.remove('admin-only'); }
    let companyCancel = $('#cancelCompanyDetails');
    if (!companyCancel) {
      companyCancel = document.createElement('button');
      companyCancel.id = 'cancelCompanyDetails';
      companyCancel.type = 'button';
      companyCancel.className = 'secondary-button company-details-cancel';
      companyCancel.textContent = 'Cancel';
      companyCancel.hidden = true;
      companySave?.insertAdjacentElement('afterend', companyCancel);
      companyCancel.addEventListener('click', () => {
        Object.entries(data.company).forEach(([name, value]) => { if (companyForm.elements[name] && name !== 'date_issued') companyForm.elements[name].value = value; });
        editableFields.forEach(input => { input.disabled = true; });
        companyEdit.hidden = false;
        if (companySave) companySave.hidden = true;
        companyCancel.hidden = true;
      });
    }
    companyCancel.hidden = true;
    let companyEdit = $('#editCompanyDetails');
    if (!companyEdit) {
      companyEdit = document.createElement('button');
      companyEdit.id = 'editCompanyDetails';
      companyEdit.type = 'button';
      companyEdit.className = 'secondary-button admin-only';
      companyEdit.textContent = 'Edit';
      changeCompanyPassword?.before(companyEdit);
      companyEdit.addEventListener('click', () => {
        editableFields.forEach(input => { input.disabled = false; });
        companyEdit.hidden = true;
        if (companySave) companySave.hidden = false;
        companyCancel.hidden = false;
      });
    }
    let companyDetailsActions = $('#companyDetailsActions');
    if (!companyDetailsActions) {
      companyDetailsActions = document.createElement('div');
      companyDetailsActions.id = 'companyDetailsActions';
      companyDetailsActions.className = 'company-detail-actions';
      changeCompanyPassword?.before(companyDetailsActions);
    }
    companyDetailsActions.append(companyEdit);
    if (companySave) companyDetailsActions.append(companySave);
    companyDetailsActions.append(companyCancel);

    let companyPasswordActions = $('#companyPasswordActions');
    if (!companyPasswordActions) {
      companyPasswordActions = document.createElement('div');
      companyPasswordActions.id = 'companyPasswordActions';
      companyPasswordActions.className = 'company-password-actions';
      companyDetailsActions.after(companyPasswordActions);
    }
    if (changeCompanyPassword) companyPasswordActions.append(changeCompanyPassword);
    if (companyPasswordEditor) companyPasswordActions.append(companyPasswordEditor);
    if (saveCompanyPassword) companyPasswordActions.append(saveCompanyPassword);
    if (cancelCompanyPassword) companyPasswordActions.append(cancelCompanyPassword);
    companyEdit.hidden = !data.is_admin;
  }
  $$('.member-change-password').forEach(button => button.addEventListener('click', () => { const memberId = button.dataset.memberChangePassword; const editor = $(`[data-member-password-editor="${memberId}"]`); const saveButton = $(`[data-member-save="${memberId}"]`); if (editor) { editor.hidden = false; button.hidden = true; if (saveButton) saveButton.hidden = false; editor.querySelector('input')?.focus(); } }));
  $$('.member-password-cancel').forEach(button => button.addEventListener('click', () => { const memberId = button.dataset.memberPasswordCancel; const editor = $(`[data-member-password-editor="${memberId}"]`); const changeButton = $(`[data-member-change-password="${memberId}"]`); const saveButton = $(`[data-member-save="${memberId}"]`); if (editor) { editor.hidden = true; editor.querySelector('input').value = ''; } if (changeButton) changeButton.hidden = false; if (saveButton) saveButton.hidden = true; }));
  $$('.member-role-select').forEach(select => select.addEventListener('change', () => {
    const saveButton = $(`[data-member-role-save="${select.dataset.memberRole}"]`);
    if (saveButton) saveButton.hidden = select.value === select.dataset.savedRole;
  }));
  $$('.member-role-save').forEach(button => button.addEventListener('click', async () => {
    const memberId = button.dataset.memberRoleSave;
    const select = $(`[data-member-role="${memberId}"]`);
    const response = await fetch(`/api/organisation/members/${memberId}`, { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ role: select.value }) });
    if (response.ok) { await loadOrganisation(); toast('Team member role updated.'); } else toast('Unable to update team member role.');
  }));
  $$('.member-save').forEach(button => button.addEventListener('click', async () => {
    const memberId = button.dataset.memberSave;
    const response = await fetch(`/api/organisation/members/${memberId}`, { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ password: $(`[data-member-password="${memberId}"]`).value }) });
    if (response.ok) { await loadOrganisation(); toast('Team member password updated.'); } else toast('Unable to update team member password.');
  }));
  $$('.member-deactivate').forEach(button => button.addEventListener('click', async () => {
    if (!window.confirm('Deactivate this team member?')) return;
    const response = await fetch(`/api/organisation/members/${button.dataset.memberDeactivate}`, { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ is_active: false }) });
    if (response.ok) { await loadOrganisation(); toast('Team member deactivated.'); } else toast('Unable to deactivate team member.');
  }));
}

function stakeholderMarkup(kind, stakeholder) {
  return `<form class="stakeholder-row" data-stakeholder-kind="${kind}" data-stakeholder-id="${stakeholder.id}"><div class="stakeholder-fields"><label>Name<input name="name" value="${stakeholder.name}" readonly></label><label>Registration no<input name="reg_no" value="${stakeholder.reg_no}" readonly></label><label>Email<input name="email" type="email" value="${stakeholder.email}" readonly></label><label>Phone<input name="phone" value="${stakeholder.phone}" readonly></label><label class="stakeholder-wide">Address<textarea name="address" rows="2" readonly>${stakeholder.address}</textarea></label></div><div class="stakeholder-actions"><button class="secondary-button stakeholder-edit" type="button">Edit</button><button class="primary-button stakeholder-save" type="submit" hidden>Save</button><button class="text-button stakeholder-cancel" type="button" hidden>Cancel</button></div></form>`;
}

function stakeholderAddMarkup(kind) {
  return `<form class="stakeholder-add-form" data-stakeholder-add="${kind}" hidden><div class="stakeholder-fields"><label>Name<input name="name" required></label><label>Registration no<input name="reg_no" required></label><label>Email<input name="email" type="email"></label><label>Phone<input name="phone"></label><label class="stakeholder-wide">Address<textarea name="address" rows="3"></textarea></label></div><div class="stakeholder-actions"><button class="primary-button" type="submit">Save</button><button class="text-button stakeholder-add-cancel" type="button">Cancel</button></div></form>`;
}

function ensureStakeholdersView() {
  const content = $('.content');
  if (!content || $('#stakeholdersView')) return;
  const organisationHead = $('[data-view-panel="organization"] .page-head');
  if (organisationHead && !$('#stakeholdersLink')) {
    const button = document.createElement('button');
    button.className = 'secondary-button admin-only';
    button.id = 'stakeholdersLink';
    button.type = 'button';
    button.hidden = true;
    button.textContent = 'View stakeholders';
    button.addEventListener('click', () => showView('stakeholders'));
    organisationHead.append(button);
  }
  const view = document.createElement('section');
  view.className = 'view';
  view.id = 'stakeholdersView';
  view.hidden = true;
  view.dataset.viewPanel = 'stakeholders';
  view.innerHTML = '<div class="page-head"><div><span class="eyebrow">Organisation</span><h2>Stakeholders</h2><p>View and update clients, contractors, and consultants.</p></div><button class="secondary-button" id="backToOrganisation" type="button">Back to Organisation</button></div><div class="stakeholder-sections"><section class="settings-card stakeholder-section"><div class="stakeholder-section-heading"><h3>Clients</h3><button class="icon-button stakeholder-add-button" data-stakeholder-add-toggle="clients" type="button" aria-label="Add client">＋</button></div><div id="clientList" class="stakeholder-list"></div></section><section class="settings-card stakeholder-section"><div class="stakeholder-section-heading"><h3>Contractors</h3><button class="icon-button stakeholder-add-button" data-stakeholder-add-toggle="contractors" type="button" aria-label="Add contractor">＋</button></div><div id="contractorList" class="stakeholder-list"></div></section><section class="settings-card stakeholder-section"><div class="stakeholder-section-heading"><h3>Consultants</h3><button class="icon-button stakeholder-add-button" data-stakeholder-add-toggle="consultants" type="button" aria-label="Add consultant">＋</button></div><div id="consultantList" class="stakeholder-list"></div></section></div>';
  content.append(view);
  $('#backToOrganisation').addEventListener('click', () => showView('organization'));
  view.querySelectorAll('.stakeholder-list').forEach(list => list.addEventListener('submit', saveStakeholder));
  view.querySelectorAll('[data-stakeholder-add-toggle]').forEach(button => button.addEventListener('click', () => toggleStakeholderAdd(button.dataset.stakeholderAddToggle)));
}

function renderStakeholders(data) {
  ensureStakeholdersView();
  const lists = { clients: $('#clientList'), contractors: $('#contractorList'), consultants: $('#consultantList') };
  Object.entries(lists).forEach(([kind, target]) => {
    if (target) target.innerHTML = (data[kind] || []).map(item => stakeholderMarkup(kind, item)).join('') + stakeholderAddMarkup(kind) || '<p class="member-empty">No records found.</p>';
  });
  document.querySelectorAll('.stakeholder-edit').forEach(button => button.addEventListener('click', () => setStakeholderEditMode(button.closest('form'), true)));
  document.querySelectorAll('.stakeholder-cancel').forEach(button => button.addEventListener('click', () => { const form = button.closest('form'); form.reset(); setStakeholderEditMode(form, false); }));
  document.querySelectorAll('.stakeholder-add-form').forEach(form => { form.addEventListener('submit', addStakeholder); form.querySelector('.stakeholder-add-cancel').addEventListener('click', () => { form.reset(); form.hidden = true; }); });
}

function setStakeholderEditMode(form, editing) {
  form.querySelectorAll('input, textarea').forEach(input => { input.readOnly = !editing; });
  form.querySelector('.stakeholder-edit').hidden = editing;
  form.querySelector('.stakeholder-save').hidden = !editing;
  form.querySelector('.stakeholder-cancel').hidden = !editing;
}

function toggleStakeholderAdd(kind) {
  const form = document.querySelector(`[data-stakeholder-add="${kind}"]`);
  if (form) form.hidden = !form.hidden;
}

async function addStakeholder(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const response = await fetch(`/api/stakeholders/${form.dataset.stakeholderAdd}`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.fromEntries(new FormData(form))) });
  if (response.ok) { await loadStakeholders(); toast('Stakeholder added.'); } else toast('Unable to add stakeholder.');
}

async function loadStakeholders() {
  if (!canViewStakeholders) return;
  const response = await fetch('/api/stakeholders');
  if (response.ok) renderStakeholders(await response.json());
}

async function saveStakeholder(event) {
  event.preventDefault();
  const form = event.target.closest('form');
  if (!form) return;
  const response = await fetch(`/api/stakeholders/${form.dataset.stakeholderKind}/${form.dataset.stakeholderId}`, { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.fromEntries(new FormData(form))) });
  if (response.ok) { form.classList.add('is-saved'); setStakeholderEditMode(form, false); setTimeout(() => form.classList.remove('is-saved'), 900); toast('Stakeholder details saved and logged.'); } else toast('Unable to save stakeholder details.');
}

async function loadOrganisation() {
  const response = await fetch('/api/organisation');
  if (!response.ok) return;
  const data = await response.json();
  renderOrganisation(data);
  if (data.is_admin) await loadStakeholders();
  const accountForm = $('#accountForm');
  if (accountForm) Object.entries(data.current_user).forEach(([name, value]) => { if (accountForm.elements[name]) accountForm.elements[name].value = value; });
}

function beginCalendarEdit(eventId) {
  const event = calendarEvents.find(item => item.id === eventId);
  if (!event || event.source !== 'event') return;
  editingCalendarEventId = eventId;
  $('#calendarTitle').value = event.title;
  $('#calendarDescription').value = event.event_description || '';
  $('#calendarProject').value = event.project_id;
  $('#calendarDate').value = event.date;
  $('#calendarStart').value = event.start_time || '';
  $('#calendarEnd').value = event.end_time || '';
  $('#calendarSubmitButton').textContent = 'Save changes';
  $('#calendarCancelEdit').hidden = false;
  $('#calendarDeleteButton').hidden = false;
  const [year, month, day] = event.date.split('-').map(Number);
  selectedCalendarDate = new Date(year, month - 1, day);
  calendarDate = new Date(year, month - 1, 1);
  renderCalendar();
}

function resetCalendarForm() {
  editingCalendarEventId = null;
  $('#calendarForm').reset();
  $('#calendarDate').value = calendarDateKey(selectedCalendarDate);
  $('#calendarSubmitButton').textContent = 'Add to calendar';
  $('#calendarCancelEdit').hidden = true;
  $('#calendarDeleteButton').hidden = true;
}
function showMeeting(index) {
  const meeting = meetings[index];
  const detail = $('#minuteDetail');
  if (!detail || !meeting) return;
  detail.innerHTML = `<span class="eyebrow">${meeting[1]}</span><h3>${meeting[0]}</h3><p>Project: ${meeting[2]}</p><hr><h4>Key decisions</h4><ol><li>Confirm foundation work by 15 May.</li><li>Approve the HVAC specification change.</li><li>Submit revised drawings by 12 May.</li></ol><button class="source-link">▤ Open source notes</button>`;
}
function renderDocuments() {
  const target = $('#documentGrid');
  if (target) target.innerHTML = documents.map(document => `<article class="document-card"><span class="stat-icon orange">▤</span><h3>${document[0]}</h3><p>${document[1]}<br>${document[2]}</p><button class="text-button" data-toast="Document preview is ready for backend connection.">Open document →</button></article>`).join('');
}
function showView(name) {
  if (name === 'stakeholders' && !canViewStakeholders) return;
  $$('.view').forEach(view => view.classList.toggle('is-active', view.dataset.viewPanel === name));
  $$('.nav-item').forEach(item => item.classList.toggle('is-active', item.dataset.view === name));
  $('#appShell')?.classList.toggle('chat-view-active', name === 'chat');
  $('.content')?.classList.toggle('dashboard-view-active', name === 'dashboard');
  $('.content')?.classList.toggle('meeting-view-active', name === 'meetings');
  if ($('#pageTitle')) $('#pageTitle').textContent = titleCase(name);
  $('#appShell')?.classList.remove('menu-open');
  sessionStorage.setItem('activeView', name);
}
function toast(message) {
  const target = $('#toast'); target.textContent = message; target.classList.add('show');
  clearTimeout(window.toastTimer); window.toastTimer = setTimeout(() => target.classList.remove('show'), 2400);
}
function escapeHtml(value) {
  return String(value || '').replace(/[&<>'"]/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'}[character]));
}
function renderAssistantAnswer(answer) {
  if (answer.needs_project) {
    const confirmation = answer.confirmation_required && answer.projects?.[0] ? `<div class="assistant-confirmation"><button type="button" data-confirm-project="${escapeHtml(answer.projects[0])}">Yes</button><button type="button" data-reject-project="true">No</button></div>` : '';
    return `<p>${escapeHtml(answer.message)}</p>${confirmation}${(answer.projects || []).length && !answer.confirmation_required ? `<ul>${answer.projects.map(project => `<li>${escapeHtml(project)}</li>`).join('')}</ul>` : ''}`;
  }
  if (answer.needs_scope) return `<p>${escapeHtml(answer.message)}</p><div class="assistant-confirmation"><button type="button" data-scope="all">All projects</button><button type="button" data-scope="specific">Specific project</button></div>`;
  const points = (answer.points || []).map(point => {
    if (typeof point === 'string') return `<li>${escapeHtml(point)}</li>`;
    const items = (point.items || []).map(item => {
      if (typeof item === 'string') return `<li>${escapeHtml(item)}</li>`;
      const title = item.item || item.title || item.description || '';
      const details = [item.owner || item.assigned_to, item.due_date, item.priority, item.status].filter(Boolean).join(' · ');
      return `<li><strong>${escapeHtml(title)}</strong>${details ? `<small>${escapeHtml(details)}</small>` : ''}</li>`;
    }).join('');
    return `<li class="assistant-project-group"><strong>${escapeHtml(point.project || 'Project')}</strong>${items ? `<ul>${items}</ul>` : ''}</li>`;
  }).join('');
  const sources = (answer.sources || []).map(source => `<li><a href="${escapeHtml(source.meeting_url)}">${escapeHtml(source.label)}</a> · <a href="${escapeHtml(source.pdf_url)}">Download PDF</a></li>`).join('');
  return `<p>${escapeHtml(answer.summary)}</p>${points ? `<h4>Key points</h4><ul>${points}</ul>` : ''}${answer.analysis ? `<h4>Suggested next step</h4><p>${escapeHtml(answer.analysis)}</p>` : ''}${sources ? `<h4>Sources</h4><ul>${sources}</ul>` : ''}`;
}
function chatStorageKey(target) {
  return target.id === 'assistantMessages' ? 'jarvis-assistant-panel-chat-v2' : 'jarvis-assistant-page-chat-v2';
}
function saveChatMessage(target, role, html) {
  const key = chatStorageKey(target);
  const history = JSON.parse(sessionStorage.getItem(key) || '[]');
  history.push({role, html});
  sessionStorage.setItem(key, JSON.stringify(history));
}
function appendChatMessage(target, role, html) {
  const message = document.createElement('div');
  message.className = role === 'user' ? 'bubble user-bubble' : 'bubble agent-bubble';
  message.innerHTML = html;
  target.append(message);
  return message;
}
function restoreChat(target) {
  if (!target) return;
  const history = JSON.parse(sessionStorage.getItem(chatStorageKey(target)) || '[]');
  if (!history.length) return;
  target.querySelectorAll('.bubble, .agent-message').forEach(message => message.remove());
  history.forEach(item => appendChatMessage(target, item.role, item.html));
}
function downloadChat(target, filename) {
  const blob = new Blob([target.innerText.trim()], {type: 'text/plain;charset=utf-8'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}
async function sendMessage(input, target, modelSelect) {
  let value = input.value.trim();
  const pendingScopeQuestion = target.dataset.pendingScopeQuestion;
  if (pendingScopeQuestion) {
    if (target.dataset.awaitingSpecificProject === 'true') {
      if (!value) return;
      value = `${value} ${pendingScopeQuestion}`;
    } else if (!value || /^(all|all projects|every project)$/i.test(value)) {
      value = `For all projects, ${pendingScopeQuestion}`;
    } else {
      value = `${value} ${pendingScopeQuestion}`;
    }
    delete target.dataset.pendingScopeQuestion;
    delete target.dataset.awaitingSpecificProject;
  }
  if (!value) return;
  if (target.dataset.pendingQuestionDisplayed !== 'true') {
    const message = appendChatMessage(target, 'user', escapeHtml(value));
    saveChatMessage(target, 'user', message.innerHTML);
  }
  delete target.dataset.pendingQuestionDisplayed;
  input.value = '';
  const answer = document.createElement('div'); answer.className = 'bubble agent-bubble'; answer.textContent = 'Checking the authorised project records...'; target.append(answer); target.scrollTop = target.scrollHeight;
  let data = null;
  try {
    const response = await fetch('/api/assistant/chat', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ question: value, model: modelSelect?.value || 'gemini' }) });
    data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Assistant request failed.');
    answer.innerHTML = renderAssistantAnswer(data);
    answer.querySelector('[data-confirm-project]')?.addEventListener('click', event => {
      input.value = `${event.currentTarget.dataset.confirmProject} ${value}`;
      sendMessage(input, target, modelSelect);
    });
    answer.querySelector('[data-reject-project]')?.addEventListener('click', () => {
      answer.innerHTML = '<p>Okay. Please type the project name you would like to use.</p>';
      saveChatMessage(target, 'agent', answer.innerHTML);
      input.focus();
    });
    answer.querySelector('[data-scope="all"]')?.addEventListener('click', () => {
      input.value = `For all projects, ${value}`;
      sendMessage(input, target, modelSelect);
    });
    answer.querySelector('[data-scope="specific"]')?.addEventListener('click', () => {
      target.dataset.pendingScopeQuestion = value;
      target.dataset.awaitingSpecificProject = 'true';
      answer.innerHTML = '<p>Type the project name in the message box, then press Enter.</p>';
      saveChatMessage(target, 'agent', answer.innerHTML);
      input.focus();
    });
    answer.querySelector('[data-scope="specific"]')?.addEventListener('click', () => {
      target.dataset.pendingScopeQuestion = value;
      target.dataset.awaitingSpecificProject = 'true';
      answer.innerHTML = '<p>Type the project name in the message box, then press Enter.</p>';
      saveChatMessage(target, 'agent', answer.innerHTML);
      input.focus();
    });
  } catch (error) { answer.textContent = error.message; }
  if (!data?.confirmation_required) saveChatMessage(target, 'agent', answer.innerHTML);
  target.scrollTop = target.scrollHeight;
}

async function loadProjects() {
  const response = await fetch('/api/projects');
  if (response.ok) {
    projects = await response.json();
    renderProjects();
    const params = new URLSearchParams(window.location.search);
    const requestedProjectId = params.get('project_id') || '';
    const requestedCalendarEventId = params.get('calendar_event_id') || '';
    if (params.get('view') === 'projects' && /^\d+$/.test(requestedProjectId)) {
      const panel = document.getElementById(`project-details-${requestedProjectId}`);
      const card = panel?.closest('.project-directory-card');
      if (card) {
        showView('projects');
        if (requestedCalendarEventId && /^\d+$/.test(requestedCalendarEventId)) {
          const calendarPanel = card.querySelector('.project-calendar-panel');
          const calendarToggle = card.querySelector('.project-calendar-toggle');
          if (calendarPanel && calendarToggle) {
            calendarPanel.hidden = false;
            calendarToggle.textContent = 'Hide calendar';
            calendarToggle.setAttribute('aria-expanded', 'true');
            await loadProjectCalendar(calendarPanel, requestedCalendarEventId);
          }
        } else if (panel.hidden) {
          card.querySelector('.project-directory-actions .project-details-toggle')?.click();
        }
        if (!requestedCalendarEventId) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      history.replaceState(null, '', window.location.pathname);
    }
  }
}
async function loadMeetings() {
  const response = await fetch('/api/meetings');
  if (response.ok) { meetings = await response.json(); renderMeetings(); }
}
loadProjects(); loadMeetings(); loadCalendar(); loadOrganisation(); ensureStakeholdersView(); renderDocuments();
$('#projectsNavToggle')?.addEventListener('click', () => {
  const submenu = $('#projectSubmenu');
  const expanded = $('#projectsNavToggle').getAttribute('aria-expanded') === 'true';
  $('#projectsNavToggle').setAttribute('aria-expanded', String(!expanded));
  submenu?.classList.toggle('is-collapsed', expanded);
  showView('projects');
});
$$('.nav-item').forEach(button => button.addEventListener('click', () => showView(button.dataset.view)));
$$('[data-view-link], [data-view-jump]').forEach(link => link.addEventListener('click', event => { event.preventDefault(); showView(link.dataset.viewLink || link.dataset.viewJump); }));
$('#mobileMenu')?.addEventListener('click', () => $('#appShell').classList.toggle('menu-open'));
const assistantPanel = $('#assistantPanel');
const assistantToggleButton = $('#assistantToggleButton');
const assistantGreeting = $('#assistantGreeting');
function setAssistantPanelOpen(open) {
  assistantPanel?.classList.toggle('is-collapsed', !open);
  assistantToggleButton?.setAttribute('aria-expanded', String(open));
  if (assistantToggleButton) {
    assistantToggleButton.setAttribute('aria-label', open ? 'Minimize AI chat' : 'Open AI chat');
    assistantToggleButton.title = open ? 'Minimize AI chat' : 'Open AI chat';
  }
  if (open && assistantGreeting) assistantGreeting.hidden = true;
}
setAssistantPanelOpen(false);
assistantToggleButton?.addEventListener('click', () => setAssistantPanelOpen(assistantPanel?.classList.contains('is-collapsed')));
$('#closeAssistantButton')?.addEventListener('click', () => setAssistantPanelOpen(false));
if (assistantGreeting && !sessionStorage.getItem('jarvis-assistant-greeting-shown')) {
  window.setTimeout(() => {
    if (!$('#appShell')?.classList.contains('chat-view-active') && assistantPanel?.classList.contains('is-collapsed')) {
      assistantGreeting.hidden = false;
      sessionStorage.setItem('jarvis-assistant-greeting-shown', 'true');
      window.setTimeout(() => { assistantGreeting.hidden = true; }, 10000);
    }
  }, 900);
}
$('#projectSearch')?.addEventListener('input', event => renderProjects(projects.filter(project => project.name.toLowerCase().includes(event.target.value.toLowerCase()))));
$('#projectFilter')?.addEventListener('change', event => renderProjects(event.target.value === 'all' ? projects : projects.filter(project => project.status === event.target.value)));
$('#dashboardProjectSearch')?.addEventListener('input', event => renderProjects(projects.filter(project => project.name.toLowerCase().includes(event.target.value.toLowerCase()))));
$('#dashboardProjectFilter')?.addEventListener('change', event => renderProjects(event.target.value === 'all' ? projects : projects.filter(project => project.status === event.target.value)));
$('#meetingSearch')?.addEventListener('input', event => renderMeetings(meetings.filter(meeting => `${meeting.title} ${meeting.project} ${meeting.revision}`.toLowerCase().includes(event.target.value.toLowerCase()))));
$('#calendarPrevious')?.addEventListener('click', () => { calendarDate = new Date(calendarDate.getFullYear(), calendarDate.getMonth() - 1, 1); renderCalendar(); });
$('#calendarNext')?.addEventListener('click', () => { calendarDate = new Date(calendarDate.getFullYear(), calendarDate.getMonth() + 1, 1); renderCalendar(); });
$('#calendarCancelEdit')?.addEventListener('click', resetCalendarForm);
$('#calendarDeleteButton')?.addEventListener('click', async () => {
  if (!editingCalendarEventId || !window.confirm('Delete this calendar event?')) return;
  const eventId = editingCalendarEventId.replace('event-', '');
  const response = await fetch(`/api/calendar-events/${eventId}`, { method: 'DELETE' });
  if (!response.ok) { toast('Unable to delete calendar event.'); return; }
  calendarEvents = calendarEvents.filter(item => item.id !== editingCalendarEventId);
  resetCalendarForm();
  renderCalendar();
  await loadProjects();
  toast('Calendar event deleted.');
});
$('#calendarForm')?.addEventListener('submit', async event => {
  event.preventDefault();
  const isEditing = Boolean(editingCalendarEventId);
  const endpoint = isEditing ? `/api/calendar-events/${editingCalendarEventId.replace('event-', '')}` : '/api/calendar-events';
  const response = await fetch(endpoint, { method: isEditing ? 'PUT' : 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ title: $('#calendarTitle').value, event_description: $('#calendarDescription').value, project_id: $('#calendarProject').value, date: $('#calendarDate').value, start_time: $('#calendarStart').value, end_time: $('#calendarEnd').value }) });
  if (!response.ok) { toast('Unable to add calendar event.'); return; }
  const savedEvent = await response.json();
  if (isEditing) calendarEvents = calendarEvents.map(item => item.id === savedEvent.id ? savedEvent : item);
  else calendarEvents.push(savedEvent);
  const [year, month, day] = savedEvent.date.split('-').map(Number);
  selectedCalendarDate = new Date(year, month - 1, day);
  calendarDate = new Date(year, month - 1, 1);
  resetCalendarForm();
  renderCalendar();
  toast(isEditing ? 'Calendar event updated.' : 'Meeting added to the shared calendar.');
});
$$('[data-open-modal]').forEach(button => button.addEventListener('click', () => { $('#modalBackdrop').hidden = false; $('#' + button.dataset.openModal).hidden = false; }));
$$('[data-close-modal]').forEach(button => button.addEventListener('click', () => { $$('.modal').forEach(modal => modal.hidden = true); $('#modalBackdrop').hidden = true; }));
$('#modalBackdrop')?.addEventListener('click', () => $$('[data-close-modal]')[0]?.click());
$$('[data-toast]').forEach(button => button.addEventListener('click', () => toast(button.dataset.toast)));
function startPortfolioQuestion(input, target, modelSelect, question) {
  const userMessage = appendChatMessage(target, 'user', escapeHtml(question));
  saveChatMessage(target, 'user', userMessage.innerHTML);
  const scopeMessage = appendChatMessage(target, 'agent', '<p>Would you like to search all projects or one specific project? You can choose below, type a project name, or press Enter to search all projects.</p><div class="assistant-confirmation"><button type="button" data-scope="all">All projects</button><button type="button" data-scope="specific">Specific project</button></div>');
  saveChatMessage(target, 'agent', scopeMessage.innerHTML);
  target.dataset.pendingScopeQuestion = question;
  scopeMessage.querySelector('[data-scope="all"]')?.addEventListener('click', () => {
    input.value = '';
    target.dataset.pendingQuestionDisplayed = 'true';
    sendMessage(input, target, modelSelect);
  });
  scopeMessage.querySelector('[data-scope="specific"]')?.addEventListener('click', () => {
    target.dataset.awaitingSpecificProject = 'true';
    scopeMessage.querySelector('p').textContent = 'Type the project name in the message box, then press Enter.';
    saveChatMessage(target, 'agent', scopeMessage.innerHTML);
    input.focus();
  });
  target.scrollTop = target.scrollHeight;
}
$$('[data-question]').forEach(button => button.addEventListener('click', () => {
  const input = button.closest('.chat-page') ? $('#chatInput') : $('#assistantInput');
  const target = button.closest('.chat-page') ? $('#chatMessages') : $('#assistantMessages');
  const modelSelect = button.closest('.chat-page') ? $('#chatModel') : $('#assistantModel');
  if (input) {
    const question = button.dataset.question;
    if (/pending|status/i.test(question)) {
      startPortfolioQuestion(input, target, modelSelect, question);
      return;
    }
    input.value = question;
    input.focus();
  }
}));
async function loadAssistantModels() {
  const response = await fetch('/api/assistant/models');
  if (!response.ok) return;
  const data = await response.json();
  ['#assistantModel', '#chatModel'].forEach(selector => { const select = $(selector); if (select) select.innerHTML = (data.models || []).map(model => `<option value="${escapeHtml(model.id)}">${escapeHtml(model.label)}</option>`).join(''); });
}
loadAssistantModels();
$('#assistantForm')?.addEventListener('submit', event => { event.preventDefault(); sendMessage($('#assistantInput'), $('#assistantMessages'), $('#assistantModel')); });
$('#chatForm')?.addEventListener('submit', event => { event.preventDefault(); sendMessage($('#chatInput'), $('#chatMessages'), $('#chatModel')); });
[$('#assistantInput'), $('#chatInput')].forEach(input => input?.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    input.form?.requestSubmit();
  }
}));
restoreChat($('#assistantMessages'));
restoreChat($('#chatMessages'));
showView(sessionStorage.getItem('activeView') || 'dashboard');
$('#downloadAssistantChat')?.addEventListener('click', () => downloadChat($('#assistantMessages'), 'jarvis-assistant-chat.txt'));
$('#downloadChatPage')?.addEventListener('click', () => downloadChat($('#chatMessages'), 'jarvis-chat.txt'));
$('.logout-button')?.addEventListener('click', () => {
  sessionStorage.removeItem('jarvis-assistant-panel-chat');
  sessionStorage.removeItem('jarvis-assistant-page-chat');
  sessionStorage.removeItem('jarvis-assistant-panel-chat-v2');
  sessionStorage.removeItem('jarvis-assistant-page-chat-v2');
  sessionStorage.removeItem('jarvis-assistant-greeting-shown');
});
$('#projectForm')?.addEventListener('submit', async event => { event.preventDefault(); const response = await fetch('/api/projects', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: $('#newProjectName').value, description: $('#newProjectDescription')?.value || '', status: 'planning'}) }); if (response.ok) { await loadProjects(); toast('Project created.'); $('[data-close-modal]').click(); } else { toast('Unable to create project.'); } });
$('#meetingForm')?.addEventListener('submit', async event => { event.preventDefault(); const projectId = $('#meetingProject')?.value; const response = await fetch(`/api/projects/${projectId}/meetings`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({title: $('#meetingTitle')?.value || '', description: ''}) }); if (response.ok) { toast('Meeting saved.'); $('[data-close-modal]').click(); } else { toast('Unable to save meeting.'); } });
$('#settingsForm')?.addEventListener('submit', event => { event.preventDefault(); document.body.classList.toggle('compact', $('#densityToggle').checked); toast('Preferences saved.'); });
$('#companyForm')?.addEventListener('submit', async event => {
  event.preventDefault();
  const companyDetails = Object.fromEntries(new FormData(event.target));
  delete companyDetails.company_password;
  const response = await fetch('/api/organisation', { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(companyDetails) });
  if (response.ok) { renderOrganisation(await response.json()); toast('Company details saved.'); } else toast('Unable to save company details.');
});
$('#changeCompanyPassword')?.addEventListener('click', event => { const editor = $('.company-password-editor'); const cancelButton = $('#cancelCompanyPassword'); const saveButton = $('#saveCompanyPassword'); if (editor) { editor.hidden = false; event.currentTarget.hidden = true; if (cancelButton) cancelButton.hidden = false; if (saveButton) saveButton.hidden = false; editor.querySelector('input')?.focus(); } });
$('#memberForm')?.addEventListener('submit', async event => {
  event.preventDefault();
  const response = await fetch('/api/organisation/members', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.fromEntries(new FormData(event.target))) });
  const result = await response.json();
  if (response.ok) { event.target.reset(); await loadOrganisation(); toast(result.reactivated ? 'Past team member reactivated.' : 'Team member added.'); } else toast(result.error || 'Unable to add team member.');
});
$('#accountForm')?.addEventListener('submit', async event => {
  event.preventDefault();
  const response = await fetch('/api/account', { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.fromEntries(new FormData(event.target))) });
  if (response.ok) { const user = await response.json(); event.target.elements.password.value = ''; event.target.elements.role.value = user.role; toast('Account details saved.'); } else toast('Unable to save account details.');
});
$('#changeAccountPassword')?.addEventListener('click', event => {
  $('.account-password-editor').hidden = false;
  $('#saveAccountPassword').hidden = false;
  $('#cancelAccountPassword').hidden = false;
  event.currentTarget.hidden = true;
  $('.account-password-editor input')?.focus();
});
$('#cancelAccountPassword')?.addEventListener('click', () => {
  $('.account-password-editor input').value = '';
  $('.account-password-editor').hidden = true;
  $('#saveAccountPassword').hidden = true;
  $('#cancelAccountPassword').hidden = true;
  $('#changeAccountPassword').hidden = false;
});
$('#saveAccountPassword')?.addEventListener('click', async () => {
  const passwordInput = $('.account-password-editor input');
  if (!passwordInput.value) { toast('Enter a new password first.'); return; }
  const response = await fetch('/api/account', { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ password: passwordInput.value }) });
  if (!response.ok) { toast('Unable to change password.'); return; }
  passwordInput.value = '';
  $('.account-password-editor').hidden = true;
  $('#saveAccountPassword').hidden = true;
  $('#cancelAccountPassword').hidden = true;
  $('#changeAccountPassword').hidden = false;
  toast('Password changed.');
});
const initialView = new URLSearchParams(window.location.search).get('view') || sessionStorage.getItem('activeView');
if (initialView) showView(initialView);

function updateMeetingProjectDetails() {
  const selector = $('#meetingProjectSelect');
  if (selector?.disabled) return;
  const option = selector?.selectedOptions[0];
  if ($('#meetingProjectSite')) $('#meetingProjectSite').value = option?.dataset.site || '';
  if ($('#meetingCompany')) $('#meetingCompany').value = option?.dataset.company || '';
  if ($('#meetingClient')) $('#meetingClient').value = option?.dataset.client || '';
  if ($('#meetingContractor')) $('#meetingContractor').value = option?.dataset.contractor || '';
  if ($('#meetingConsultant')) $('#meetingConsultant').value = option?.dataset.consultant || '';
}

function filterMeetingProjects(query = '') {
  const input = $('#meetingProjectSearch');
  const options = $('#meetingProjectOptions');
  if (!input || !options) return;
  const normalizedQuery = query.trim().toLocaleLowerCase();
  let visibleCount = 0;
  options.querySelectorAll('.meeting-project-option').forEach(option => {
    const matches = option.dataset.projectName.toLocaleLowerCase().includes(normalizedQuery);
    option.hidden = !matches;
    if (matches) visibleCount += 1;
  });
  const emptyMessage = options.querySelector('.meeting-project-empty');
  if (emptyMessage) emptyMessage.hidden = visibleCount > 0;
}

function closeMeetingProjectOptions() {
  const input = $('#meetingProjectSearch');
  const options = $('#meetingProjectOptions');
  if (!input || !options) return;
  options.hidden = true;
  input.setAttribute('aria-expanded', 'false');
  const selected = $('#meetingProjectSelect')?.selectedOptions[0];
  if (selected?.value) input.value = selected.textContent.trim();
}

function selectMeetingProject(option) {
  const input = $('#meetingProjectSearch');
  const selector = $('#meetingProjectSelect');
  const projectId = $('#meetingProjectId');
  if (!input || !selector || !projectId) return;
  selector.value = option.dataset.projectId;
  projectId.value = option.dataset.projectId;
  input.value = option.dataset.projectName;
  $('#meetingProjectOptions')?.querySelectorAll('.meeting-project-option').forEach(item => {
    item.setAttribute('aria-selected', String(item === option));
  });
  updateMeetingProjectDetails();
  closeMeetingProjectOptions();
}

const meetingProjectSearch = $('#meetingProjectSearch');
meetingProjectSearch?.addEventListener('focus', () => {
  const options = $('#meetingProjectOptions');
  meetingProjectSearch.select();
  filterMeetingProjects();
  if (options) options.hidden = false;
  meetingProjectSearch.setAttribute('aria-expanded', 'true');
});
meetingProjectSearch?.addEventListener('input', () => {
  const selector = $('#meetingProjectSelect');
  if (selector) selector.value = '';
  const projectId = $('#meetingProjectId');
  if (projectId) projectId.value = '';
  updateMeetingProjectDetails();
  filterMeetingProjects(meetingProjectSearch.value);
  const options = $('#meetingProjectOptions');
  if (options) options.hidden = false;
  meetingProjectSearch.setAttribute('aria-expanded', 'true');
});
$('#meetingProjectOptions')?.addEventListener('mousedown', event => {
  if (event.target.closest('.meeting-project-option')) event.preventDefault();
});
$('#meetingProjectOptions')?.addEventListener('click', event => {
  const option = event.target.closest('.meeting-project-option');
  if (option) selectMeetingProject(option);
});
meetingProjectSearch?.addEventListener('keydown', event => {
  if (event.key === 'ArrowDown') {
    event.preventDefault();
    $('#meetingProjectOptions')?.querySelector('.meeting-project-option:not([hidden])')?.focus();
  } else if (event.key === 'Escape') {
    closeMeetingProjectOptions();
  } else if (event.key === 'Enter' && $('#meetingProjectOptions:not([hidden])')) {
    const firstOption = $('#meetingProjectOptions .meeting-project-option:not([hidden])');
    if (firstOption) {
      event.preventDefault();
      selectMeetingProject(firstOption);
    }
  }
});
$('#meetingProjectOptions')?.addEventListener('keydown', event => {
  const options = [...$('#meetingProjectOptions').querySelectorAll('.meeting-project-option:not([hidden])')];
  const currentIndex = options.indexOf(event.target);
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    if (options.length) {
      const nextIndex = currentIndex < 0
        ? (event.key === 'ArrowDown' ? 0 : options.length - 1)
        : (currentIndex + (event.key === 'ArrowDown' ? 1 : options.length - 1)) % options.length;
      options[nextIndex].focus();
    }
  } else if (event.key === 'Enter' && event.target.matches('.meeting-project-option')) {
    event.preventDefault();
    selectMeetingProject(event.target);
  } else if (event.key === 'Escape') {
    meetingProjectSearch?.focus();
    closeMeetingProjectOptions();
  }
});
document.addEventListener('click', event => {
  if (!event.target.closest('.meeting-project-search')) closeMeetingProjectOptions();
});
$('.meeting-form')?.addEventListener('submit', event => {
  const projectId = $('#meetingProjectId');
  if (projectId && !projectId.value) {
    event.preventDefault();
    toast('Search for and select a project before creating the meeting.');
    meetingProjectSearch?.focus();
  }
});

function addMeetingTask(sectionIndex, container) {
  const row = document.createElement('div');
  row.className = 'task-row';
  row.innerHTML = `<span class="task-number"></span><textarea name="task_title_${sectionIndex}" rows="2" required placeholder="Task title"></textarea><textarea name="task_description_${sectionIndex}" rows="2" placeholder="Task description"></textarea><textarea name="task_assigned_to_${sectionIndex}" rows="2" placeholder="Assigned to (add multiple names)" spellcheck="false"></textarea><input name="task_due_date_${sectionIndex}" type="date"><select name="task_status_${sectionIndex}" class="task-status status-open"><option value="Open">Open</option><option value="Closed">Closed</option><option value="Pending">Pending</option><option value="FYI">For Info</option></select><select name="task_priority_${sectionIndex}" class="task-priority"><option value="High">High</option><option value="Medium">Medium</option><option value="Low">Low</option><option value="None" selected>None</option></select><textarea name="task_notes_${sectionIndex}" rows="2" placeholder="Remarks"></textarea><button class="text-button remove-task" type="button">Remove</button>`;
  container.querySelector('.task-rows').append(row);
  updateTaskSectionValues(container);
  row.querySelector('.remove-task').addEventListener('click', () => {
    row.remove();
    updateMeetingTaskNumbers();
  });
  row.querySelector('.task-status').addEventListener('change', updateTaskStatusColor);
  row.querySelector('.task-priority').addEventListener('change', updateTaskPriorityColor);
  updateMeetingTaskNumbers();
}

function updateMeetingTaskNumbers() {
  $$('#meetingSections .task-row .task-number').forEach((number, index) => {
    number.textContent = String(index + 1);
  });
}

function updateTaskSectionValues(section) {
  const header = section.querySelector('.task-columns');
  if (header) header.innerHTML = '<span>No.</span><span>Action / Key Item</span><span>Description</span><span>Assigned_To</span><span>Due Date</span><span>Progress</span><span>Priority</span><span>Remarks</span><span></span>';
}

function bindActionItemScroll(section) {
  const columns = section.querySelector('.task-columns');
  const rows = section.querySelector('.task-rows');
  if (!columns || !rows) return;
  let headerViewport = columns.parentElement;
  if (!headerViewport.classList.contains('task-header-scroll')) {
    headerViewport = document.createElement('div');
    headerViewport.className = 'task-header-scroll';
    columns.replaceWith(headerViewport);
    headerViewport.append(columns);
  }
  if (headerViewport.dataset.scrollBound === 'true') return;
  headerViewport.dataset.scrollBound = 'true';
  headerViewport.addEventListener('scroll', () => { rows.scrollLeft = headerViewport.scrollLeft; });
  rows.addEventListener('scroll', () => { headerViewport.scrollLeft = rows.scrollLeft; });
}

function updateTaskStatusColor(event) {
  const select = event.target;
  select.className = `task-status status-${select.value.toLowerCase().replaceAll(' ', '-')}`;
}

function updateTaskPriorityColor(event) {
  const select = event.target;
  select.className = `task-priority priority-${select.value.toLowerCase()}`;
}

function addMeetingSection() {
  const sections = $('#meetingSections');
  const index = Number(sections?.dataset.sectionCount || 0);
  if (sections) sections.dataset.sectionCount = String(index + 1);
  const section = document.createElement('div');
  section.className = 'meeting-section-editor';
  section.dataset.sectionIndex = String(index);
  section.innerHTML = `<input type="hidden" name="section_index" value="${index}"><div class="section-editor-head"><input name="section_date" type="date" required><input name="section_title" required placeholder="Section title"><button class="text-button remove-section" type="button">Remove</button></div><div class="task-columns" aria-hidden="true"><span>No.</span><span>Action / Key Item</span><span>Description</span><span>Assigned_To</span><span>Due Date</span><span>Progress</span><span>Priority</span><span>Remarks</span><span></span></div><div class="task-rows"></div><button class="text-button add-task" type="button">＋ Add row</button>`;
  sections.append(section);
  section.querySelector('.add-task').addEventListener('click', () => addMeetingTask(index, section));
  section.querySelector('.remove-section').addEventListener('click', () => {
    section.remove();
    updateMeetingTaskNumbers();
  });
  bindActionItemScroll(section);
  addMeetingTask(index, section);
}

$('#meetingProjectSelect')?.addEventListener('change', updateMeetingProjectDetails);
updateMeetingProjectDetails();
$('#addSection')?.addEventListener('click', addMeetingSection);
$$('.add-task').forEach(button => button.addEventListener('click', () => { const section = button.closest('.meeting-section-editor'); addMeetingTask(section.dataset.sectionIndex, section); }));
$$('.meeting-section-editor').forEach(section => {
  updateTaskSectionValues(section);
  section.querySelector('input[name="section_date"]')?.addEventListener('change', () => updateTaskSectionValues(section));
  section.querySelector('input[name="section_title"]')?.addEventListener('input', () => updateTaskSectionValues(section));
  bindActionItemScroll(section);
});
updateMeetingTaskNumbers();
const focusTaskId = new URLSearchParams(window.location.search).get('task_id');
if (focusTaskId) {
  const focusedTask = document.querySelector(`.task-row[data-task-id="${focusTaskId}"]`);
  focusedTask?.classList.add('is-focused-task');
  focusedTask?.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
}
$$('.remove-task, .remove-section').forEach(button => button.addEventListener('click', () => {
  button.closest('.task-row, .meeting-section-editor').remove();
  updateMeetingTaskNumbers();
}));
$$('.task-status').forEach(select => select.addEventListener('change', updateTaskStatusColor));
$$('.task-priority').forEach(select => select.addEventListener('change', updateTaskPriorityColor));
$('#addParticipant')?.addEventListener('click', () => {
  const row = document.createElement('div');
  row.className = 'participant-row';
  row.innerHTML = '<input name="participants" placeholder="Participant name" list="participantNames"><input name="participant_company" placeholder="Company" list="participantCompanies"><button class="text-button remove-participant" type="button">Remove</button>';
  $('#participants').append(row);
  row.querySelector('.remove-participant').addEventListener('click', () => row.remove());
});
$$('.remove-participant').forEach(button => button.addEventListener('click', () => button.closest('.participant-row').remove()));
