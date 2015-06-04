define([
    'app'
], function(app) {
    'use strict';

    var CHART_DATA_LIMIT = 50;

    return {
        parent: 'project_details',
        url: 'flaky_tests/?date',
        templateUrl: 'partials/project-flaky-tests.html',
        controller: function($scope, $state, projectData, flakyTestsData) {
            var genChartData = function(data) {
                return {
                    data: data.map(function(day) {
                        var className = 'result-unknown';
                        if (data.isOverallGraph || day.test_existed) {
                            className = day.flaky_runs > 0 ? 'result-failed' : 'result-passed';
                        }

                        return {
                            className: className,
                            value: day.flaky_runs,
                            data: day
                        };
                    }),
                    options: {
                        limit: CHART_DATA_LIMIT,
                        linkFormatter: function(item) {
                            return $state.href('project_flaky_tests', {date: item.date});
                        },
                        tooltipFormatter: function(item) {
                            var ratio = 0;
                            if (item.passing_runs > 0) {
                                ratio = (100 * item.flaky_runs/item.passing_runs).toFixed(2);
                            }
                            return '<h5>' + item.date + '</h5>' +
                                '<p>Flaky runs: ' + item.flaky_runs +
                                ' (' + ratio + '% of passing runs)</p>';
                        }
                     }
                };
            };

            // We set isOverallGraph so genChartData can differentiate individual test
            // history graph from the overall graph
            flakyTestsData.chartData.isOverallGraph = true;
            $scope.chartData = genChartData(flakyTestsData.chartData);

            flakyTestsData.flakyTests.map(function(test) {
                test.chartData = genChartData(test.history);

                // We create an element and get its outerHTML to escape the output.
                var text = document.createTextNode(test.output);
                var pre = document.createElement('pre');
                pre.appendChild(text);
                test.tooltip = pre.outerHTML;
            });
            $scope.flakyTests = flakyTestsData.flakyTests;

            $scope.date = flakyTestsData.date;
        },
        resolve: {
            flakyTestsData: function($http, $stateParams, projectData) {
                var url = '/api/0/projects/' + projectData.id + '/flaky_tests/?date=' +
                    ($stateParams.date || '');
                return $http.get(url).then(function(response) {
                    return response.data;
                });
            }
        }
    };
});