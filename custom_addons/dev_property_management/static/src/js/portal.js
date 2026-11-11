document.addEventListener('DOMContentLoaded', function() {
    const citySelect = document.getElementById('city_id');

    citySelect.addEventListener('change', function() {
        if (citySelect.value !== "") {
            document.getElementById('filterForm').submit();
        }
    });
});