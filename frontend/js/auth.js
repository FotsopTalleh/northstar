/**
 * auth.js — Handles login and signup on the index page
 */

document.addEventListener("DOMContentLoaded", () => {
  // If already logged in, redirect to dashboard
  if (getToken()) {
    window.location.href = "/dashboard.html";
    return;
  }

  const loginTab   = document.getElementById("tab-login");
  const signupTab  = document.getElementById("tab-signup");
  const loginForm  = document.getElementById("form-login");
  const signupForm = document.getElementById("form-signup");

  loginTab.addEventListener("click", () => switchTab("login"));
  signupTab.addEventListener("click", () => switchTab("signup"));

  function switchTab(tab) {
    loginTab.classList.toggle("active", tab === "login");
    signupTab.classList.toggle("active", tab === "signup");
    loginForm.classList.toggle("d-none", tab !== "login");
    signupForm.classList.toggle("d-none", tab !== "signup");
  }

  // ── Login ──────────────────────────────────────────────────────────────────
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = loginForm.querySelector("button[type=submit]");
    btn.disabled = true;
    btn.textContent = "Signing in…";
    try {
      const data = await apiFetch("/api/auth/login", "POST", {
        email: document.getElementById("login-email").value.trim(),
        password: document.getElementById("login-password").value,
      });
      setToken(data.token);
      setUser(data.user);
      window.location.href = "/dashboard.html";
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "Sign In";
    }
  });

  // ── Signup ─────────────────────────────────────────────────────────────────
  signupForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = signupForm.querySelector("button[type=submit]");
    btn.disabled = true;
    btn.textContent = "Creating account…";
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
      btn.disabled = false;
      btn.textContent = "Create Account";
    }
  });
});
