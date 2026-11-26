const tasks = [
  ["Order flour", "2027-03-02"], ["Pay the electricity bill", "2027-03-05"],
  ["Call the plumber", "2027-03-08"], ["Renew the permit", "2027-03-12"],
  ["Plan the spring menu", "2027-04-01"],
];
const today = new Date();
document.getElementById("today").textContent = today.toLocaleDateString();
if (!localStorage.getItem("tasks")) localStorage.setItem("tasks", JSON.stringify(tasks));
setTimeout(() => {
  for (const [name, due] of JSON.parse(localStorage.getItem("tasks"))) {
    const item = document.createElement("li");
    item.textContent = `${name}, due ${due}`;
    if (new Date(due) < today) item.className = "overdue";
    document.getElementById("tasks").appendChild(item);
  }
}, 500);
