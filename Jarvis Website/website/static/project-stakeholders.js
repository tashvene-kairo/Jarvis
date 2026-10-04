document.addEventListener('DOMContentLoaded', () => {
  const projectForm = document.querySelector('#projectSetupForm');
  if (!projectForm) return;

  const clientSearch = projectForm.querySelector('#existingClientSearch');
  const clientOptions = projectForm.querySelector('#existingClientOptions');
  const existingClientId = projectForm.querySelector('#existingClientId');
  const clearClientButton = projectForm.querySelector('[data-clear-existing-client]');
  const clientFields = {
    name: projectForm.querySelector('[data-existing-client-field="name"]'),
    regNo: projectForm.querySelector('[data-existing-client-field="regNo"]'),
    email: projectForm.querySelector('[data-existing-client-field="email"]'),
    phone: projectForm.querySelector('[data-existing-client-field="phone"]'),
    address: projectForm.querySelector('[data-existing-client-field="address"]'),
  };
  const clientResults = [...(clientOptions?.querySelectorAll('.client-search-option') || [])];
  const newClientFields = ['client_name', 'client_reg_no', 'client_email', 'client_phone_number', 'client_address']
    .map(name => projectForm.querySelector(`[name="${name}"]`));

  function hideClientOptions() {
    if (!clientOptions || !clientSearch) return;
    clientOptions.hidden = true;
    clientSearch.setAttribute('aria-expanded', 'false');
    clientSearch.removeAttribute('aria-activedescendant');
  }

  function showClientOptions(query = '') {
    if (!clientOptions || !clientSearch) return;
    const normalizedQuery = query.trim().toLocaleLowerCase();
    let visibleCount = 0;
    clientResults.forEach(option => {
      const matches = option.dataset.name.toLocaleLowerCase().includes(normalizedQuery);
      option.hidden = !matches;
      if (matches) visibleCount += 1;
    });
    const emptyMessage = clientOptions.querySelector('.client-search-empty');
    if (emptyMessage) emptyMessage.hidden = visibleCount > 0;
    clientOptions.hidden = false;
    clientSearch.setAttribute('aria-expanded', 'true');
    clientSearch.dataset.visibleCount = String(visibleCount);
  }

  function clearExistingClient() {
    if (!clientSearch || !existingClientId) return;
    existingClientId.value = '';
    clientSearch.value = '';
    Object.values(clientFields).forEach(field => { if (field) field.value = ''; });
    clientResults.forEach(option => option.setAttribute('aria-selected', 'false'));
    if (clearClientButton) clearClientButton.hidden = true;
    hideClientOptions();
  }

  function selectExistingClient(option) {
    if (!clientSearch || !existingClientId) return;
    existingClientId.value = option.dataset.clientId;
    clientSearch.value = option.dataset.name;
    Object.entries(clientFields).forEach(([key, field]) => {
      if (field) field.value = option.dataset[key] || '';
    });
    clientResults.forEach(result => result.setAttribute('aria-selected', String(result === option)));
    newClientFields.forEach(field => { if (field) field.value = ''; });
    if (clearClientButton) clearClientButton.hidden = false;
    hideClientOptions();
  }

  if (clientSearch && clientOptions && existingClientId) {
    clientSearch.addEventListener('focus', () => showClientOptions(clientSearch.value));
    clientSearch.addEventListener('input', () => {
      const query = clientSearch.value;
      clearExistingClient();
      clientSearch.value = query;
      showClientOptions(query);
    });
    clientSearch.addEventListener('keydown', event => {
      const visibleOptions = clientResults.filter(option => !option.hidden);
      if (event.key === 'Escape') {
        hideClientOptions();
      } else if (event.key === 'ArrowDown' && visibleOptions.length) {
        event.preventDefault();
        visibleOptions[0].focus();
      }
    });
    clientOptions.addEventListener('click', event => {
      const option = event.target.closest('.client-search-option');
      if (!option) return;
      selectExistingClient(option);
    });
    document.addEventListener('pointerdown', event => {
      if (!event.target.closest('.client-search')) hideClientOptions();
    });
    document.addEventListener('focusin', event => {
      if (!event.target.closest('.client-search')) hideClientOptions();
    });
    clientOptions.addEventListener('keydown', event => {
      const visibleOptions = clientResults.filter(option => !option.hidden);
      const currentIndex = visibleOptions.indexOf(event.target);
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const offset = event.key === 'ArrowDown' ? 1 : -1;
        visibleOptions[(currentIndex + offset + visibleOptions.length) % visibleOptions.length]?.focus();
      } else if (event.key === 'Enter' && event.target.matches('.client-search-option')) {
        event.preventDefault();
        selectExistingClient(event.target);
        clientSearch.focus();
      } else if (event.key === 'Escape') {
        hideClientOptions();
        clientSearch.focus();
      }
    });
    clearClientButton?.addEventListener('click', () => {
      clearExistingClient();
      clientSearch.focus();
    });
    newClientFields.forEach(field => field?.addEventListener('input', () => {
      if (field.value) clearExistingClient();
    }));

    const savedOption = clientResults.find(option => option.dataset.clientId === existingClientId.value);
    if (savedOption) selectExistingClient(savedOption);
    else clearExistingClient();
  }

  function closeContractorSearch(party) {
    const searchInput = party.querySelector('.contractor-search-input');
    const options = party.querySelector('.contractor-search-options');
    if (options) options.hidden = true;
    searchInput?.setAttribute('aria-expanded', 'false');
  }

  function filterContractorOptions(party, query = '') {
    const searchInput = party.querySelector('.contractor-search-input');
    const options = party.querySelector('.contractor-search-options');
    if (!searchInput || !options) return;
    const normalizedQuery = query.trim().toLocaleLowerCase();
    let visibleCount = 0;
    options.querySelectorAll('.contractor-search-option').forEach(option => {
      const matches = option.dataset.name.toLocaleLowerCase().includes(normalizedQuery);
      option.hidden = !matches;
      if (matches) visibleCount += 1;
    });
    const emptyMessage = options.querySelector('.client-search-empty');
    if (emptyMessage) emptyMessage.hidden = visibleCount > 0;
    options.hidden = false;
    searchInput.setAttribute('aria-expanded', 'true');
  }

  function clearContractorSelection(party, preserveSearch = false, clearNewFields = true) {
    const searchInput = party.querySelector('.contractor-search-input');
    const selectedId = party.querySelector('.existing-contractor-id');
    const clearButton = party.querySelector('.clear-contractor-selection');
    if (selectedId) selectedId.value = '';
    if (!preserveSearch && searchInput) searchInput.value = '';
    party.querySelectorAll('[data-existing-contractor-field]').forEach(field => { field.value = ''; });
    party.querySelectorAll('.contractor-search-option').forEach(option => option.setAttribute('aria-selected', 'false'));
    if (clearNewFields) party.querySelectorAll('[name^="contractor_"]').forEach(field => { field.value = ''; });
    if (clearButton) clearButton.hidden = true;
    closeContractorSearch(party);
  }

  function selectExistingContractor(party, option) {
    const searchInput = party.querySelector('.contractor-search-input');
    const selectedId = party.querySelector('.existing-contractor-id');
    const clearButton = party.querySelector('.clear-contractor-selection');
    if (!searchInput || !selectedId) return;
    selectedId.value = option.dataset.contractorId;
    searchInput.value = option.dataset.name;
    Object.entries({
      regNo: 'regNo',
      email: 'email',
      phone: 'phone',
      address: 'address',
    }).forEach(([fieldName, dataName]) => {
      const field = party.querySelector(`[data-existing-contractor-field="${fieldName}"]`);
      if (field) field.value = option.dataset[dataName] || '';
    });
    party.querySelectorAll('.contractor-search-option').forEach(result => {
      result.setAttribute('aria-selected', String(result === option));
    });
    party.querySelectorAll('[name^="contractor_"]').forEach(field => { field.value = ''; });
    if (clearButton) clearButton.hidden = false;
    closeContractorSearch(party);
  }

  function closeConsultantSearch(party) {
    const searchInput = party.querySelector('.consultant-search-input');
    const options = party.querySelector('.consultant-search-options');
    if (options) options.hidden = true;
    searchInput?.setAttribute('aria-expanded', 'false');
  }

  function filterConsultantOptions(party, query = '') {
    const searchInput = party.querySelector('.consultant-search-input');
    const options = party.querySelector('.consultant-search-options');
    if (!searchInput || !options) return;
    const normalizedQuery = query.trim().toLocaleLowerCase();
    let visibleCount = 0;
    options.querySelectorAll('.consultant-search-option').forEach(option => {
      const matches = option.dataset.name.toLocaleLowerCase().includes(normalizedQuery);
      option.hidden = !matches;
      if (matches) visibleCount += 1;
    });
    const emptyMessage = options.querySelector('.client-search-empty');
    if (emptyMessage) emptyMessage.hidden = visibleCount > 0;
    options.hidden = false;
    searchInput.setAttribute('aria-expanded', 'true');
  }

  function clearConsultantSelection(party, preserveSearch = false, clearNewFields = true) {
    const searchInput = party.querySelector('.consultant-search-input');
    const selectedId = party.querySelector('.existing-consultant-id');
    const clearButton = party.querySelector('.clear-consultant-selection');
    if (selectedId) selectedId.value = '';
    if (!preserveSearch && searchInput) searchInput.value = '';
    party.querySelectorAll('[data-existing-consultant-field]').forEach(field => { field.value = ''; });
    if (clearNewFields) party.querySelectorAll('[name^="consultant_"]').forEach(field => { field.value = ''; });
    party.querySelectorAll('.consultant-search-option').forEach(option => option.setAttribute('aria-selected', 'false'));
    if (clearButton) clearButton.hidden = true;
    closeConsultantSearch(party);
  }

  function selectExistingConsultant(party, option) {
    const searchInput = party.querySelector('.consultant-search-input');
    const selectedId = party.querySelector('.existing-consultant-id');
    const clearButton = party.querySelector('.clear-consultant-selection');
    if (!searchInput || !selectedId) return;
    selectedId.value = option.dataset.consultantId;
    searchInput.value = option.dataset.name;
    Object.entries({
      regNo: 'regNo',
      email: 'email',
      phone: 'phone',
      address: 'address',
    }).forEach(([fieldName, dataName]) => {
      const field = party.querySelector(`[data-existing-consultant-field="${fieldName}"]`);
      if (field) field.value = option.dataset[dataName] || '';
    });
    party.querySelectorAll('[name^="consultant_"]').forEach(field => { field.value = ''; });
    party.querySelectorAll('.consultant-search-option').forEach(result => {
      result.setAttribute('aria-selected', String(result === option));
    });
    if (clearButton) clearButton.hidden = false;
    closeConsultantSearch(party);
  }

  projectForm.addEventListener('focusin', event => {
    const consultantSearch = event.target.closest('.consultant-search');
    const consultantSearchInput = event.target.closest('.consultant-search-input');
    if (consultantSearch) {
      projectForm.querySelectorAll('.contractor-party').forEach(closeContractorSearch);
      if (consultantSearchInput) filterConsultantOptions(consultantSearch.closest('.consultant-party'), consultantSearchInput.value);
      return;
    }
    projectForm.querySelectorAll('.consultant-party').forEach(closeConsultantSearch);
    const search = event.target.closest('.contractor-search');
    const searchInput = event.target.closest('.contractor-search-input');
    if (search) {
      const activeParty = search.closest('.contractor-party');
      projectForm.querySelectorAll('.contractor-party').forEach(party => {
        if (party !== activeParty) closeContractorSearch(party);
      });
      if (searchInput) filterContractorOptions(activeParty, searchInput.value);
      return;
    }
    projectForm.querySelectorAll('.contractor-party').forEach(closeContractorSearch);
  });
  projectForm.addEventListener('focusout', event => {
    const party = event.target.closest('.consultant-party');
    if (party && !event.relatedTarget?.closest?.('.consultant-search')) closeConsultantSearch(party);
  });
  projectForm.addEventListener('input', event => {
    const consultantSearchInput = event.target.closest('.consultant-search-input');
    if (consultantSearchInput) {
      const party = consultantSearchInput.closest('.consultant-party');
      const query = consultantSearchInput.value;
      clearConsultantSelection(party, true);
      consultantSearchInput.value = query;
      filterConsultantOptions(party, query);
      return;
    }
    const searchInput = event.target.closest('.contractor-search-input');
    if (searchInput) {
      const party = searchInput.closest('.contractor-party');
      const query = searchInput.value;
      clearContractorSelection(party, true);
      searchInput.value = query;
      filterContractorOptions(party, query);
      return;
    }
    const newContractorField = event.target.closest('.contractor-party [name^="contractor_"]');
    if (newContractorField?.value) clearContractorSelection(newContractorField.closest('.contractor-party'), false, false);
    const newConsultantField = event.target.closest('.consultant-party [name^="consultant_"]');
    if (newConsultantField) clearConsultantSelection(newConsultantField.closest('.consultant-party'), false, false);
  });
  projectForm.addEventListener('click', event => {
    const consultantSearchInput = event.target.closest('.consultant-search-input');
    if (consultantSearchInput) {
      filterConsultantOptions(consultantSearchInput.closest('.consultant-party'), consultantSearchInput.value);
      return;
    }
    const consultantOption = event.target.closest('.consultant-search-option');
    if (consultantOption) {
      selectExistingConsultant(consultantOption.closest('.consultant-party'), consultantOption);
      return;
    }
    const clearConsultantButton = event.target.closest('.clear-consultant-selection');
    if (clearConsultantButton) {
      const party = clearConsultantButton.closest('.consultant-party');
      clearConsultantSelection(party);
      party.querySelector('.consultant-search-input')?.focus();
      return;
    }
    const searchInput = event.target.closest('.contractor-search-input');
    if (searchInput) {
      filterContractorOptions(searchInput.closest('.contractor-party'), searchInput.value);
      return;
    }
    const option = event.target.closest('.contractor-search-option');
    if (option) {
      selectExistingContractor(option.closest('.contractor-party'), option);
      return;
    }
    const cancelButton = event.target.closest('.cancel-contractor-party');
    if (cancelButton) {
      const party = cancelButton.closest('.contractor-party');
      if (party?.classList.contains('is-added')) party.remove();
      return;
    }
    const cancelConsultantButton = event.target.closest('.cancel-consultant-party');
    if (cancelConsultantButton) {
      const party = cancelConsultantButton.closest('.consultant-party');
      if (party?.classList.contains('is-added')) party.remove();
      return;
    }
    const clearButton = event.target.closest('.clear-contractor-selection');
    if (clearButton) {
      const party = clearButton.closest('.contractor-party');
      clearContractorSelection(party);
      party.querySelector('.contractor-search-input')?.focus();
    }
  });
  projectForm.addEventListener('keydown', event => {
    const consultantSearchInput = event.target.closest('.consultant-search-input');
    if (consultantSearchInput && event.key === 'ArrowDown') {
      const option = consultantSearchInput.closest('.consultant-party').querySelector('.consultant-search-option:not([hidden])');
      if (option) {
        event.preventDefault();
        option.focus();
      }
    } else if (event.target.matches('.consultant-search-option') && ['ArrowDown', 'ArrowUp'].includes(event.key)) {
      const visibleOptions = [...event.target.closest('.consultant-search-options').querySelectorAll('.consultant-search-option:not([hidden])')];
      const currentIndex = visibleOptions.indexOf(event.target);
      const offset = event.key === 'ArrowDown' ? 1 : -1;
      event.preventDefault();
      visibleOptions[(currentIndex + offset + visibleOptions.length) % visibleOptions.length]?.focus();
    } else if (event.key === 'Escape' && event.target.closest('.consultant-party')) {
      const party = event.target.closest('.consultant-party');
      closeConsultantSearch(party);
      party.querySelector('.consultant-search-input')?.focus();
    }
    const searchInput = event.target.closest('.contractor-search-input');
    if (searchInput && event.key === 'ArrowDown') {
      const option = searchInput.closest('.contractor-party').querySelector('.contractor-search-option:not([hidden])');
      if (option) {
        event.preventDefault();
        option.focus();
      }
    } else if (event.key === 'Escape' && event.target.closest('.contractor-party')) {
      closeContractorSearch(event.target.closest('.contractor-party'));
    }
  });
  document.addEventListener('pointerdown', event => {
    if (!event.target.closest('.consultant-search')) {
      projectForm.querySelectorAll('.consultant-party').forEach(closeConsultantSearch);
    }
    if (!event.target.closest('.contractor-search')) {
      projectForm.querySelectorAll('.contractor-party').forEach(closeContractorSearch);
    }
  });

  projectForm.querySelectorAll('.add-party').forEach(button => button.addEventListener('click', () => {
    const target = document.getElementById(button.dataset.target);
    const template = target?.querySelector('.repeatable-party');
    if (!target || !template) return;
    const party = template.cloneNode(true);
    party.querySelectorAll('input').forEach(input => {
      input.value = '';
      input.removeAttribute('value');
    });
    party.querySelectorAll('.contractor-search-options').forEach(options => { options.hidden = true; });
    party.querySelectorAll('.consultant-search-options').forEach(options => { options.hidden = true; });
    party.querySelectorAll('.contractor-search-input').forEach(input => input.setAttribute('aria-expanded', 'false'));
    party.querySelectorAll('.consultant-search-input').forEach(input => input.setAttribute('aria-expanded', 'false'));
    party.querySelectorAll('.clear-contractor-selection').forEach(button => { button.hidden = true; });
    party.querySelectorAll('.contractor-search-option').forEach(option => option.setAttribute('aria-selected', 'false'));
    party.querySelectorAll('.consultant-search-option').forEach(option => option.setAttribute('aria-selected', 'false'));
    party.querySelectorAll('.existing-consultant-id').forEach(input => { input.value = ''; });
    party.querySelectorAll('.clear-consultant-selection').forEach(button => { button.hidden = true; });
    if (button.dataset.target === 'consultants') {
      const searchInput = party.querySelector('.consultant-search-input');
      const options = party.querySelector('.consultant-search-options');
      const index = target.querySelectorAll('.consultant-party').length;
      const searchId = `consultantSearch-${index}`;
      const optionsId = `consultantOptions-${index}`;
      if (searchInput && options) {
        party.querySelector('label[for="existingConsultantSearch"]')?.setAttribute('for', searchId);
        searchInput.id = searchId;
        searchInput.setAttribute('aria-controls', optionsId);
        options.id = optionsId;
      }
    }
    if (button.dataset.target === 'contractors') {
      party.classList.add('is-added');
      const cancelButton = document.createElement('button');
      cancelButton.className = 'secondary-button cancel-contractor-party';
      cancelButton.type = 'button';
      cancelButton.textContent = 'Cancel';
      party.appendChild(cancelButton);
    } else if (button.dataset.target === 'consultants') {
      party.classList.add('consultant-party', 'is-added');
      const cancelButton = document.createElement('button');
      cancelButton.className = 'secondary-button cancel-consultant-party';
      cancelButton.type = 'button';
      cancelButton.textContent = 'Cancel';
      party.appendChild(cancelButton);
    }
    if (button.dataset.label) {
      const heading = document.createElement('strong');
      heading.className = 'repeatable-party-label';
      heading.textContent = button.dataset.label;
      party.prepend(heading);
    }
    target.appendChild(party);
  }));
});
