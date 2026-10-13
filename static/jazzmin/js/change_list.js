(function($) {
    'use strict';

    $.fn.search_filters = function () {
        $(this).change(function () {
            const $field = $(this);
            const $option = $field.find('option:selected');
            const select_name = $option.data('name');
            if (select_name) {
                $field.attr('name', select_name);
            } else {
                $field.removeAttr('name');
            }
        });
        $(this).trigger('change');
    };

    function getMinimuInputLength(element) {
        return window.filterInputLength[element.data('name')] ?? window.filterInputLengthDefault;
    }

    function searchFilters() {
        const $ele = $('.search-filter');
        $ele.search_filters();
        $ele.each(function () {
            const $this = $(this);
            $this.select2({  width: '100%', minimumInputLength: getMinimuInputLength($this) });
        });

        const $mptt = $('.search-filter-mptt');
        if ($mptt.length) {
            $mptt.search_filters();
            $mptt.select2({
                width: '100%',
                minimumInputLength: getMinimuInputLength($mptt),
                templateResult: function (data) {
                    if (!data.element) {
                        return data.text;
                    }
                    const $element = $(data.element);
                    let $wrapper = $('<span></span>');
                    $wrapper.attr('style', $($element[0]).attr('style'));
                    $wrapper.text(data.text);
                    return $wrapper;
                },
            });
        }
    }

    $(document).ready(function () {
        $('.related-lookup').append('<i class="fa fa-search"></i>');
        $('.actions select').addClass('form-control');
        searchFilters();
    });

})(jQuery);
