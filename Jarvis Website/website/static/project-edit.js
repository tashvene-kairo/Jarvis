document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('.project-detail-form');
  if (!form) return;

  function closeSearch(party) {
    const input = party.querySelector('.edit-stakeholder-search-input');
    const options = party.querySelector('.edit-stakeholder-options');
    if (options) options.hidden = true;
    input?.setAttribute('aria-expanded', 'false');
  }

  function filterOptions(party, query = '') {
    const input = party.querySelector('.edit-stakeholder-search-input');
    const options = party.querySelector('.edit-stakeholder-options');
    if (!input || !options) return;
    const normalizedQuery = query.trim().toLocaleLowerCase();
    let visibleCount = 0;
    options.querySelectorAll('.edit-stakeholder-option').forEach(option => {
      option.hidden = !option.dataset.name.toLocaleLowerCase().includes(normalizedQuery);
      if (!option.hidden) visibleCount += 1;
    });
    const emptyMessage = options.querySelector('.client-search-empty');
    if (emptyMessage) emptyMessage.hidden = visibleCount > 0;
    options.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  }

  function clearSelection(party, clearNewFields = true) {
    const input = party.querySelector('.edit-stakeholder-search-input');
    const selectedId = party.querySelector('.existing-stakeholder-id');
    const clearButton = party.querySelector('.clear-edit-stakeholder');
    if (input) input.value = '';
    if (selectedId) selectedId.value = '';
    party.querySelectorAll('[data-existing-field]').forEach(field => { field.value = ''; });
    party.querySelectorAll('.edit-stakeholder-option').forEach(option => option.setAttribute('aria-selected', 'false'));
    if (clearNewFields) party.querySelectorAll('[name]').forEach(field => { if (!field.classList.contains('existing-stakeholder-id')) field.value = ''; });
    if (clearButton) clearButton.hidden = true;
    closeSearch(party);
  }

  function selectOption(party, option) {
    const input = party.querySelector('.edit-stakeholder-search-input');
    const selectedId = party.querySelector('.existing-stakeholder-id');
    if (!input || !selectedId) return;
    input.value = option.dataset.name;
    selectedId.value = option.dataset.id;
    for (const key of ['regNo', 'email', 'phone', 'address']) {
      const field = party.querySelector(`[data-existing-field="${key}"]`);
      if (field) field.value = option.dataset[key] || '';
    }
    party.querySelectorAll('.edit-stakeholder-option').forEach(item => {
      item.setAttribute('aria-selected', String(item === option));
    });
    party.querySelectorAll('[name]').forEach(field => {
      if (!field.classList.contains('existing-stakeholder-id')) field.value = '';
    });
    const clearButton = party.querySelector('.clear-edit-stakeholder');
    if (clearButton) clearButton.hidden = false;
    closeSearch(party);
  }

  function showEditor(party) {
    const summary = party.querySelector('.edit-stakeholder-summary');
    const editor = party.querySelector('.edit-stakeholder-editor');
    if (summary) summary.hidden = true;
    if (editor) editor.hidden = false;
    party.querySelector('.edit-stakeholder-search-input')?.focus();
  }

  function hideEditor(party) {
    const originalId = party.dataset.originalId;
    if (originalId) {
      const option = [...party.querySelectorAll('.edit-stakeholder-option')].find(item => item.dataset.id === originalId);
      if (option) selectOption(party, option);
    } else {
      clearSelection(party);
    }
    const summary = party.querySelector('.edit-stakeholder-summary');
    const editor = party.querySelector('.edit-stakeholder-editor');
    if (summary) summary.hidden = false;
    if (editor) editor.hidden = true;
  }

  form.addEventListener('focusin', event => {
    const party = event.target.closest('.edit-stakeholder-party');
    form.querySelectorAll('.edit-stakeholder-party').forEach(other => {
      if (other !== party) closeSearch(other);
    });
    if (party && event.target.matches('.edit-stakeholder-search-input')) {
      filterOptions(party, event.target.value);
    }
  });

  form.addEventListener('focusout', event => {
    const party = event.target.closest('.edit-stakeholder-party');
    if (party && !event.relatedTarget?.closest?.('.edit-stakeholder-search')) closeSearch(party);
  });

  form.addEventListener('input', event => {
    const searchInput = event.target.closest('.edit-stakeholder-search-input');
    if (searchInput) {
      const party = searchInput.closest('.edit-stakeholder-party');
      const query = searchInput.value;
      clearSelection(party);
      searchInput.value = query;
      filterOptions(party, query);
      return;
    }
    const newField = event.target.closest('.edit-stakeholder-party [name]');
    if (newField && !newField.classList.contains('existing-stakeholder-id')) {
      clearSelection(newField.closest('.edit-stakeholder-party'), false);
    }
  });

  form.addEventListener('click', event => {
    const cancelProjectEdit = event.target.closest('.cancel-project-edit');
    if (cancelProjectEdit) {
      if (window.history.length > 1) window.history.back();
      else window.location.assign(cancelProjectEdit.dataset.fallbackUrl);
      return;
    }
    const editButton = event.target.closest('.edit-stakeholder-button');
    if (editButton) {
      showEditor(editButton.closest('.edit-stakeholder-party'));
      return;
    }
    const searchInput = event.target.closest('.edit-stakeholder-search-input');
    if (searchInput) {
      filterOptions(searchInput.closest('.edit-stakeholder-party'), searchInput.value);
      return;
    }
    const option = event.target.closest('.edit-stakeholder-option');
    if (option) {
      selectOption(option.closest('.edit-stakeholder-party'), option);
      return;
    }
    const clearButton = event.target.closest('.clear-edit-stakeholder');
    if (clearButton) {
      const party = clearButton.closest('.edit-stakeholder-party');
      clearSelection(party);
      party.querySelector('.edit-stakeholder-search-input')?.focus();
      return;
    }
    const cancelButton = event.target.closest('.cancel-edit-stakeholder');
    if (cancelButton) {
      const party = cancelButton.closest('.edit-stakeholder-party');
      if (party?.classList.contains('is-added') && !party.dataset.originalId) party.remove();
      else if (party) hideEditor(party);
      return;
    }
    const addButton = event.target.closest('.add-edit-stakeholder');
    if (!addButton) return;
    const target = document.getElementById(addButton.dataset.target);
    const template = target?.querySelector('.edit-stakeholder-party');
    if (!target || !template) return;
    const party = template.cloneNode(true);
    party.classList.add('is-added');
    party.dataset.originalId = '';
    party.querySelectorAll('input').forEach(input => { input.value = ''; });
    party.querySelectorAll('.edit-stakeholder-summary').forEach(summary => { summary.hidden = true; });
    party.querySelectorAll('.edit-stakeholder-editor').forEach(editor => { editor.hidden = false; });
    party.querySelectorAll('.edit-stakeholder-options').forEach(options => { options.hidden = true; });
    party.querySelectorAll('.edit-stakeholder-option').forEach(option => {
      option.hidden = false;
      option.setAttribute('aria-selected', 'false');
    });
    party.querySelectorAll('.edit-stakeholder-search-input').forEach(input => input.setAttribute('aria-expanded', 'false'));
    party.querySelectorAll('.clear-edit-stakeholder').forEach(button => { button.hidden = true; });
    target.append(party);
    party.querySelector('.edit-stakeholder-search-input')?.focus();
  });

  form.addEventListener('keydown', event => {
    const party = event.target.closest('.edit-stakeholder-party');
    if (!party) return;
    if (event.key === 'Escape') {
      closeSearch(party);
      party.querySelector('.edit-stakeholder-search-input')?.focus();
      return;
    }
    const visibleOptions = [...party.querySelectorAll('.edit-stakeholder-option:not([hidden])')];
    if (event.target.matches('.edit-stakeholder-search-input') && event.key === 'ArrowDown') {
      event.preventDefault();
      visibleOptions[0]?.focus();
    } else if (event.target.matches('.edit-stakeholder-option') && ['ArrowDown', 'ArrowUp'].includes(event.key)) {
      event.preventDefault();
      const index = visibleOptions.indexOf(event.target);
      const offset = event.key === 'ArrowDown' ? 1 : -1;
      visibleOptions[(index + offset + visibleOptions.length) % visibleOptions.length]?.focus();
    } else if (event.target.matches('.edit-stakeholder-option') && event.key === 'Enter') {
      event.preventDefault();
      selectOption(party, event.target);
      party.querySelector('.edit-stakeholder-search-input')?.focus();
    }
  });

  document.addEventListener('pointerdown', event => {
    if (!event.target.closest('.edit-stakeholder-search')) {
      form.querySelectorAll('.edit-stakeholder-party').forEach(closeSearch);
    }
  });
});
