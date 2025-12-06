
// Global Chart Data
var currentChartData = null;
var currentChartInstance = null;
var currentChartIndex = 0;
var currentDimensions = [];

$(document).ready(function() {
    // 1. Inject Modal HTML
    var modalHtml = `
    <div id="chart_modal_overlay" class="chart-modal-overlay">
        <div class="chart-modal">
            <div class="cm-header">
                <span class="cm-title" id="chart_modal_title">舆情数据报表</span>
                <div class="cm-actions">
                     <button id="chart_btn_download">下载图片</button>
                     <button id="chart_btn_close">×</button>
                </div>
            </div>
            <div class="cm-body" id="chart_body">
                 <div id="chart_main_container" class="chart-container"></div>
                 <div class="chart-arrow chart-prev" id="chart_prev" style="display:none;">&lt;</div>
                 <div class="chart-arrow chart-next" id="chart_next" style="display:none;">&gt;</div>
                 <div class="chart-pagination" id="chart_pagination"></div>
            </div>
            <div class="cm-footer">
                <span id="chart_footer_info">数据来源：舆情系统内部数据库</span>
            </div>
        </div>
    </div>
    `;
    $('body').append(modalHtml);

    // 2. Event Listeners
    $('#chart_btn_close').click(function() {
        $('#chart_modal_overlay').hide();
        if(currentChartInstance) {
            currentChartInstance.dispose();
            currentChartInstance = null;
        }
    });

    $('#chart_btn_download').click(function() {
        if(currentChartInstance) {
            var url = currentChartInstance.getDataURL({
                type: 'png',
                backgroundColor: '#fff'
            });
            var a = document.createElement('a');
            a.href = url;
            a.download = `舆情报表_${currentChartData.time_range}_${currentDimensions[currentChartIndex]}_${currentChartData.generated_at}.png`;
            a.click();
        }
    });
    
    $('#chart_prev').click(function() {
        if(currentChartIndex > 0) {
            currentChartIndex--;
            renderCurrentChart();
        }
    });
    
    $('#chart_next').click(function() {
        if(currentChartIndex < currentDimensions.length - 1) {
            currentChartIndex++;
            renderCurrentChart();
        }
    });

    // Window Resize
    $(window).resize(function() {
        if(currentChartInstance) {
            currentChartInstance.resize();
        }
    });
});

// Global function to be called from onclick in the HTML message
window.showChartModal = function(btn) {
    var dataJson = $(btn).attr('data-chart');
    if(!dataJson) return;
    
    try {
        currentChartData = JSON.parse(dataJson);
        currentDimensions = currentChartData.dimensions;
        currentChartIndex = 0;
        
        $('#chart_modal_title').text(currentChartData.time_range + ' 舆情数据报表');
        var footerText = `数据来源：舆情系统内部数据库 | 统计时间：${currentChartData.timeline[0]} 至 ${currentChartData.timeline[currentChartData.timeline.length-1]}`;
        $('#chart_footer_info').text(footerText);
        
        $('#chart_modal_overlay').css('display', 'flex');
        
        renderCurrentChart();
        
    } catch(e) {
        console.error("Failed to parse chart data", e);
        alert("无法打开报表：数据解析错误");
    }
};

function renderCurrentChart() {
    var dim = currentDimensions[currentChartIndex];
    var dom = document.getElementById('chart_main_container');
    
    if(currentChartInstance) {
        currentChartInstance.dispose();
    }
    
    currentChartInstance = echarts.init(dom);
    var option = getOptionForDimension(dim, currentChartData);
    
    currentChartInstance.setOption(option);
    
    updatePagination();
}

function updatePagination() {
    var total = currentDimensions.length;
    
    // Arrows
    if (total > 1) {
        $('#chart_prev').toggle(currentChartIndex > 0);
        $('#chart_next').toggle(currentChartIndex < total - 1);
    } else {
        $('#chart_prev').hide();
        $('#chart_next').hide();
    }
    
    // Dots
    var $pg = $('#chart_pagination');
    $pg.empty();
    if (total > 1) {
        for(var i=0; i<total; i++) {
            var $dot = $('<div class="chart-page-dot"></div>');
            if(i === currentChartIndex) $dot.addClass('active');
            (function(idx){
                $dot.click(function(){
                    currentChartIndex = idx;
                    renderCurrentChart();
                });
            })(i);
            $pg.append($dot);
        }
    }
}

function getOptionForDimension(dim, data) {
    var commonGrid = { left: '5%', right: '5%', bottom: '10%', containLabel: true };
    var title = { text: dim, left: 'center', textStyle: { fontSize: 16, fontFamily: 'Microsoft YaHei' } };
    var tooltip = { trigger: 'axis' };
    
    if (dim === '情感趋势') {
        return {
            title: title,
            tooltip: tooltip,
            legend: { data: ['正面', '负面', '中性'], bottom: 0 },
            grid: commonGrid,
            xAxis: { type: 'category', data: data.timeline },
            yAxis: { type: 'value' },
            series: [
                { name: '正面', type: 'line', data: data.sentiment.positive, itemStyle: { color: '#00B42A' }, smooth: true },
                { name: '负面', type: 'line', data: data.sentiment.negative, itemStyle: { color: '#F53F3F' }, smooth: true },
                { name: '中性', type: 'line', data: data.sentiment.neutral, itemStyle: { color: '#86909C' }, smooth: true }
            ]
        };
    } else if (dim === '关键词分布') {
        return {
            title: title,
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
            grid: commonGrid,
            xAxis: { type: 'category', data: data.keywords.words, axisLabel: { rotate: 45, interval: 0 } },
            yAxis: { type: 'value' },
            series: [
                { name: '频次', type: 'bar', data: data.keywords.counts, itemStyle: { color: '#5470C6' } }
            ]
        };
    } else if (dim === '来源分布') {
        var pieData = data.sources.names.map((name, i) => ({ name: name, value: data.sources.values[i] }));
        return {
            title: title,
            tooltip: { trigger: 'item' },
            legend: { bottom: 0 },
            series: [
                {
                    name: '来源占比',
                    type: 'pie',
                    radius: ['40%', '70%'],
                    avoidLabelOverlap: false,
                    itemStyle: {
                        borderRadius: 10,
                        borderColor: '#fff',
                        borderWidth: 2
                    },
                    label: { show: false, position: 'center' },
                    emphasis: {
                        label: { show: true, fontSize: 20, fontWeight: 'bold' }
                    },
                    data: pieData
                }
            ]
        };
    } else if (dim === '传播热度') {
        return {
            title: title,
            tooltip: tooltip,
            grid: commonGrid,
            xAxis: { type: 'category', data: data.timeline, boundaryGap: false },
            yAxis: { type: 'value' },
            series: [
                {
                    name: '热度',
                    type: 'line',
                    data: data.heat.values,
                    areaStyle: {},
                    itemStyle: { color: '#EE6666' },
                    markLine: {
                        data: [{ type: 'average', name: 'Avg' }]
                    }
                }
            ]
        };
    }
    return {};
}
