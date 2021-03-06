pipeline {
    agent any

    options {
        skipDefaultCheckout(true)
        // Keep the 2 most recent builds
        buildDiscarder(logRotator(numToKeepStr: '2'))
        timestamps()
    }

    environment {
      PATH="/var/lib/jenkins/miniconda3/bin:$PATH"
    }

    stages {
        stage ("Code pull"){
            steps{
                checkout scm
            }
        }

        stage('Build environment') {
            steps {
                echo "Building virtualenv"
                sh  ''' conda create --yes -n ${BUILD_TAG} python
                        source /var/lib/jenkins/miniconda3/etc/profile.d/conda.sh
                        conda activate ${BUILD_TAG}
                        pip install -r requirements.txt
                        pip install pylint
                    '''
            }
        }

        stage('Static code metrics') {
            steps {
                echo "Style check"
                sh  ''' source /var/lib/jenkins/miniconda3/etc/profile.d/conda.sh
                        conda activate ${BUILD_TAG}
                        pylint PlexBot || true
                    '''
            }
        }

        stage('Build package') {
            when {
                expression {
                    currentBuild.result == null || currentBuild.result == 'SUCCESS'
                }
            }
            steps {
                sh  './deploy/build.sh'
            }
        }
        stage('Push Image') {
            steps {
                sh './deploy/push.sh'
            }
        }
    }

    post {
        always {
            sh 'conda remove --yes -n ${BUILD_TAG} --all'
            sh 'docker system prune -a -f'
        }
    }
}
