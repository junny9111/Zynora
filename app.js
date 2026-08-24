document.addEventListener("DOMContentLoaded", () => {

  const searchInput = document.getElementById("searchInput");
  const stories = document.querySelectorAll(".story");
  const categories = document.querySelectorAll(".category");

  // Search
  if (searchInput) {
    searchInput.addEventListener("input", () => {

      const search = searchInput.value.toLowerCase().trim();

      stories.forEach((story) => {

        const title = (
          story.dataset.title ||
          story.innerText
        ).toLowerCase();

        story.style.display =
          title.includes(search) ? "" : "block";

      });

    });
  }

  // Category buttons
  categories.forEach((button) => {

    button.addEventListener("click", () => {

      categories.forEach((item) => {
        item.classList.remove("active");
      });

      button.classList.add("active");

    });

  });

  // Story selection
  stories.forEach((story) => {

    story.addEventListener("click", () => {

      const title = story.dataset.title || "Zynora Story";

      alert(
        title +
        "\n\nVideo player coming next."
      );

    });

  });

});
