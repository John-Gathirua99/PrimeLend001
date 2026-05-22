document.addEventListener('DOMContentLoaded', function () {
  const loader = document.getElementById('pageLoader');
  if (loader) {
    window.addEventListener('load', function () {
      loader.style.opacity = '0';
      loader.style.pointerEvents = 'none';
      setTimeout(function () { loader.style.display = 'none'; }, 400);
    });
  }

  const track = document.getElementById('tickerTrack');
  if (track) {
    const loans = [
      {name:'J. Mwangi', amt:'KES 45,000', loc:'Nairobi'},
      {name:'A. Ochieng', amt:'KES 120,000', loc:'Kisumu'},
      {name:'F. Kamau', amt:'KES 30,000', loc:'Thika'},
      {name:'B. Njoroge', amt:'KES 75,000', loc:'Nakuru'},
      {name:'M. Wanjiku', amt:'KES 200,000', loc:'Mombasa'},
      {name:'P. Otieno', amt:'KES 55,000', loc:'Eldoret'},
      {name:'G. Kariuki', amt:'KES 90,000', loc:'Nairobi'},
      {name:'S. Auma', amt:'KES 40,000', loc:'Kisii'},
    ];
    track.innerHTML = [...loans, ...loans].map(l =>
      `<span class="pl-ticker-item"><span class="t-name">${l.name}</span> approved <span class="t-amt">${l.amt}</span> <span class="t-loc">· ${l.loc}</span></span><span class="pl-ticker-sep">·</span>`
    ).join('');
  }

  const nav = document.getElementById('mainNav');
  if (nav) {
    window.addEventListener('scroll', function () {
      nav.classList.toggle('scrolled', window.scrollY > 20);
    }, { passive: true });
  }

  const fab = document.getElementById('chatFab');
  const win = document.getElementById('chatWindow');
  const closeBtn = document.getElementById('chatClose');
  const input = document.getElementById('chatInput');
  const sendBtn = document.getElementById('chatSend');
  const messages = document.getElementById('chatMessages');
  const suggestions = document.getElementById('chatSuggestions');

  const replies = {
    borrow: 'You can borrow up to 3× your monthly income. Minimum KES 1,000, maximum KES 500,000 depending on your trust tier.',
    interest: 'Rates range from 10–25% based on your credit score. Excellent credit gets 10%, standard credit 15–18%.',
    apply: 'Click Loans → Apply for Loan. You need your National ID, income details, and a live selfie for KYC. Takes ~3 minutes.',
    kyc: 'KYC needs a flat photo of your National ID (no glare) and a live selfie. Our AI verifies you automatically.',
    repay: 'Repay from your wallet balance or directly via M-Pesa STK push. Early repayments are penalty-free.',
    status: 'Go to Loans → My Loans to track your application status, repayment schedule, and history.',
    default: 'Happy to help! Ask about loan limits, interest rates, how to apply, or KYC requirements.',
  };

  function getReply(question) {
    const text = question.toLowerCase();
    if (/borrow|much|limit|amount|how much/.test(text)) return replies.borrow;
    if (/interest|rate|%/.test(text)) return replies.interest;
    if (/apply|how|start|begin/.test(text)) return replies.apply;
    if (/kyc|id|verify|identity|selfie/.test(text)) return replies.kyc;
    if (/repay|pay|install|payment/.test(text)) return replies.repay;
    if (/status|check|loan|track/.test(text)) return replies.status;
    return replies.default;
  }

  function addMessage(text, type) {
    const bubble = document.createElement('div');
    bubble.className = 'pl-msg ' + type;
    bubble.textContent = text;
    messages.appendChild(bubble);
    messages.scrollTop = messages.scrollHeight;
  }

  function sendMessage(text) {
    const trimmed = text.trim();
    if (!trimmed) return;
    addMessage(trimmed, 'user');
    suggestions.style.display = 'none';
    input.value = '';
    const typing = document.createElement('div');
    typing.className = 'pl-msg typing';
    typing.textContent = '…';
    messages.appendChild(typing);
    messages.scrollTop = messages.scrollHeight;
    setTimeout(function () {
      typing.remove();
      addMessage(getReply(trimmed), 'bot');
    }, 650 + Math.random() * 300);
  }

  if (fab && win) {
    fab.addEventListener('click', function () {
      win.classList.toggle('open');
      if (win.classList.contains('open')) input.focus();
    });
  }

  if (closeBtn && win) {
    closeBtn.addEventListener('click', function () {
      win.classList.remove('open');
    });
  }

  if (sendBtn && input) {
    sendBtn.addEventListener('click', function () {
      sendMessage(input.value);
    });

    input.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        sendMessage(input.value);
      }
    });
  }

  if (suggestions) {
    suggestions.querySelectorAll('.pl-chat-suggestion').forEach(function (button) {
      button.addEventListener('click', function () {
        sendMessage(button.textContent);
      });
    });
  }
});
