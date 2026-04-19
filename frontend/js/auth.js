/**
 * auth.js — Login, Signup, Forgot Password, Google Sign-In
 */

document.addEventListener("DOMContentLoaded", () => {
  if (getToken()) {
    window.location.href = "/dashboard.html";
    return;
  }

  const loginTab   = document.getElementById("tab-login");
  const signupTab  = document.getElementById("tab-signup");
  const loginForm  = document.getElementById("form-login");
  const signupForm = document.getElementById("form-signup");

  loginTab.addEventListener("click",  () => switchTab("login"));
  signupTab.addEventListener("click", () => switchTab("signup"));

  function switchTab(tab) {
    loginTab.classList.toggle("active",  tab === "login");
    signupTab.classList.toggle("active", tab === "signup");
    loginForm.classList.toggle("d-none",  tab !== "login");
    signupForm.classList.toggle("d-none", tab !== "signup");
    hideForgot();
  }

  // ── Login ──────────────────────────────────────────────────────────────────
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = loginForm.querySelector("button[type=submit]");
    setButtonLoading(btn, true);
    try {
      const data = await apiFetch("/api/auth/login", "POST", {
        email:    document.getElementById("login-email").value.trim(),
        password: document.getElementById("login-password").value,
      });
      setToken(data.token);
      setUser(data.user);
      window.location.href = "/dashboard.html";
    } catch (err) {
      showToast(err.message, "error");
      setButtonLoading(btn, false, "Sign In");
    }
  });

  // ── Signup ─────────────────────────────────────────────────────────────────
  signupForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = signupForm.querySelector("button[type=submit]");
    setButtonLoading(btn, true);
    try {
      const data = await apiFetch("/api/auth/signup", "POST", {
        email:    document.getElementById("signup-email").value.trim(),
        password: document.getElementById("signup-password").value,
        username: document.getElementById("signup-username").value.trim(),
        timezone: document.getElementById("signup-timezone").value,
      });
      setToken(data.token);
      setUser(data.user);
      window.location.href = "/dashboard.html";
    } catch (err) {
      showToast(err.message, "error");
      setButtonLoading(btn, false, "Create Account");
    }
  });

  // ── Forgot Password ─────────────────────────────────────────────────────────
  document.getElementById("btn-forgot")?.addEventListener("click", showForgot);

  document.getElementById("form-forgot")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn   = e.target.querySelector("button[type=submit]");
    const email = document.getElementById("forgot-email").value.trim();
    setButtonLoading(btn, true);
    try {
      await apiFetch("/api/auth/forgot-password", "POST", { email });
      e.target.classList.add("d-none");
      document.getElementById("forgot-success").classList.remove("d-none");
    } catch (err) {
      showToast(err.message, "error");
      setButtonLoading(btn, false, "Send Reset Link");
    }
  });
});

// ── Forgot panel helpers ────────────────────────────────────────────────────
function showForgot() {
  document.getElementById("form-login").classList.add("d-none");
  document.getElementById("forgot-panel").classList.remove("d-none");
  // Pre-fill email if already typed
  const loginEmail = document.getElementById("login-email")?.value.trim();
  if (loginEmail) document.getElementById("forgot-email").value = loginEmail;
  if (window.lucide) window.lucide.createIcons();
}

function hideForgot() {
  const panel = document.getElementById("forgot-panel");
  const form  = document.getElementById("form-login");
  if (!panel || !form) return;
  panel.classList.add("d-none");
  form.classList.remove("d-none");
  // Reset forgot success state
  document.getElementById("form-forgot")?.classList.remove("d-none");
  document.getElementById("forgot-success")?.classList.add("d-none");
}

// ── Google Sign-In callback ─────────────────────────────────────────────────
async function handleGoogleCredential(response) {
  try {
    showToast("Signing in with Google…", "info");
    const data = await apiFetch("/api/auth/google", "POST", {
      credential: response.credential,
    });
    setToken(data.token);
    setUser(data.user);
    window.location.href = "/dashboard.html";
  } catch (err) {
    showToast(err.message || "Google Sign-In failed", "error");
  }
}
