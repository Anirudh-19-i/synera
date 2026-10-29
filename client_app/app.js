// Theme: respects the OS setting on first visit, then remembers the choice.
(function () {
  var root = document.documentElement;
  var saved = null;
  try { saved = localStorage.getItem("theme"); } catch (e) {}
  var prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  root.setAttribute("data-theme", saved || (prefersDark ? "dark" : "light"));

  document.getElementById("theme-toggle").addEventListener("click", function () {
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) {}
  });
})();

// BMI calculator
function calculateBMI(heightCm, weightKg) {
  var m = heightCm / 100;
  return weightKg / (m * m);
}

function bmiCategory(bmi) {
  if (bmi < 18.5) return "Underweight";
  if (bmi < 25) return "Healthy range";
  if (bmi < 30) return "Overweight";
  return "Obese";
}

document.getElementById("bmi-form").addEventListener("submit", function (e) {
  e.preventDefault();
  var h = parseFloat(document.getElementById("height-cm").value);
  var w = parseFloat(document.getElementById("weight-kg").value);
  var out = document.getElementById("bmi-result");
  if (!h || !w) { out.textContent = "Enter both height and weight."; return; }
  var bmi = calculateBMI(h, w);
  out.textContent = "Your BMI is " + bmi.toFixed(1) + " (" + bmiCategory(bmi) + ")";
});
